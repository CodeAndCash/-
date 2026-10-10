"""Источник 2ГИС (Places API, catalog.api.2gis.com). Нужен ключ DGIS_API_KEY.

Адаптер изолирован: любая ошибка превращается в DgisError и не ломает поиск,
остальные источники продолжают работать. Телефоны 2ГИС отдаёт только ключам,
у которых в договоре открыт доступ к контактам (поле items.contact_groups)."""

from __future__ import annotations

import asyncio
import logging
import math

import aiohttp

from . import contacts as cn

SEARCH_URL = "https://catalog.api.2gis.com/3.0/items"
FIELDS = ",".join((
    "items.point",
    "items.address",
    "items.adm_div",
    "items.contact_groups",
    "items.reviews",
    "items.schedule",
))
# Страны, где у 2ГИС есть справочник организаций.
COUNTRIES = {"RU", "KZ", "KG", "UZ", "BY", "AZ", "AM", "GE", "TJ", "AE", "CY", "SA", "QA", "BH", "KW", "OM"}
DAYS = (("Mon", "Пн"), ("Tue", "Вт"), ("Wed", "Ср"), ("Thu", "Чт"), ("Fri", "Пт"), ("Sat", "Сб"), ("Sun", "Вс"))

log = logging.getLogger("parser.dgis")
_warned_no_contacts = False


class DgisError(Exception):
    pass


def covers(country: str) -> bool:
    return country.upper() in COUNTRIES


def area(bbox: tuple[float, float, float, float]) -> tuple[str, int]:
    """Центр и радиус поиска по прямоугольнику города (south, west, north, east).
    Прямоугольник 2ГИС ограничен 2 км, поэтому ищем кругом (до 50 км)."""
    south, west, north, east = bbox
    lat = (south + north) / 2
    lon = (west + east) / 2
    dy = (north - south) * 111_320 / 2
    dx = (east - west) * 111_320 * math.cos(math.radians(lat)) / 2
    radius = int(min(50_000, max(1_000, math.hypot(dx, dy))))
    return f"{lon:.6f},{lat:.6f}", radius


def _website(contact: dict) -> str:
    url = str(contact.get("url") or "").strip()
    if url.startswith(("http://", "https://")) and "link.2gis" not in url:
        return url
    text = str(contact.get("text") or "").strip()
    if text and " " not in text and "." in text:
        return text if text.startswith(("http://", "https://")) else "http://" + text
    return ""


def _contacts(item: dict) -> tuple[list[str], str, dict]:
    phones: list[str] = []
    site = ""
    extra: dict[str, str] = {}
    for group in item.get("contact_groups") or []:
        for contact in group.get("contacts") or []:
            kind = str(contact.get("type") or "")
            value = str(contact.get("value") or contact.get("text") or "").strip()
            if kind == "phone" and value and value not in phones:
                phones.append(value)
            elif kind == "website" and not site:
                site = _website(contact)
            elif kind == "email" and value:
                extra.setdefault("email", value)
            elif kind == "telegram" and value:
                extra.setdefault("tg", value)
            elif kind == "whatsapp" and value:
                extra.setdefault("wa", value)
            elif kind == "vkontakte" and value:
                extra.setdefault("vk", value)
    return phones, site, extra


def _hours(item: dict) -> str:
    schedule = item.get("schedule") or {}
    if not isinstance(schedule, dict):
        return ""
    if schedule.get("is_24x7"):
        return "Круглосуточно"
    parts = []
    for key, title in DAYS:
        day = schedule.get(key) or {}
        hours = day.get("working_hours") or []
        if hours:
            first, last = hours[0], hours[-1]
            parts.append(f"{title} {first.get('from', '')}–{last.get('to', '')}")
    return "; ".join(parts)[:300]


def _city(item: dict) -> str:
    for division in item.get("adm_div") or []:
        if division.get("type") == "city" and division.get("name"):
            return str(division["name"])
    return ""


def firm_link(item_id: str, country: str = "RU") -> str:
    firm = str(item_id or "").split("_")[0]
    if not firm.isdigit():
        return ""
    host = {"KZ": "2gis.kz", "KG": "2gis.kg", "UZ": "2gis.uz", "AE": "2gis.ae"}.get(country.upper(), "2gis.ru")
    return f"https://{host}/firm/{firm}"


def to_candidate(item: dict, country: str, city: str = "") -> dict | None:
    item_id = str(item.get("id") or "")
    name = str(item.get("name") or "").strip()
    if not item_id or not name:
        return None
    point = item.get("point") or {}
    phones, site, extra = _contacts(item)
    reviews = item.get("reviews") or {}
    rating = reviews.get("general_rating") or reviews.get("rating")
    count = reviews.get("general_review_count") or reviews.get("review_count")
    link = firm_link(item_id, country)
    try:
        rating = round(float(rating), 1) if rating else None
    except (TypeError, ValueError):
        rating = None
    try:
        count = int(count) if count else None
    except (TypeError, ValueError):
        count = None
    return {
        "key": "d:" + item_id.split("_")[0],
        "source": "dgis",
        "name": name,
        "city": _city(item) or city,
        "phone_raw": ";".join(phones),
        "url_raw": site,
        "address": str(item.get("address_name") or "").strip(),
        "map": link,
        "lat": point.get("lat"),
        "lon": point.get("lon"),
        "tags": {},
        # Соцсети приводим к тому же виду, что и у OpenStreetMap (@ник, номер WhatsApp, id ВК).
        "contacts": {key: value for key, value in cn.clean_contacts(extra, country).items()
                     if key not in ("address", "site", "map")},
        "country": country.upper(),
        "source_url": link,
        "rating": rating,
        "reviews": count,
        "hours": _hours(item),
    }


async def search(
    session: aiohttp.ClientSession,
    api_key: str,
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    max_pages: int = 3,
    page_size: int = 10,
    want: int | None = None,
    on_request=None,
    locale: str = "ru_RU",
) -> list[dict]:
    """Организации по запросу в круге вокруг города. on_request() вызывается перед
    каждым запросом и должен вернуть False, если месячный лимит исчерпан."""
    global _warned_no_contacts
    point, radius = area(bbox)
    items: list[dict] = []
    for page in range(1, max(1, max_pages) + 1):
        if on_request is not None and not await on_request():
            break
        params = {
            "q": text[:500],
            "key": api_key,
            "type": "branch",
            "point": point,
            "radius": str(radius),
            "page": str(page),
            "page_size": str(page_size),
            "fields": FIELDS,
            "locale": locale,
        }
        try:
            async with session.get(SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as response:
                data = await response.json(content_type=None)
        except asyncio.TimeoutError as exc:
            raise DgisError("2ГИС не ответил вовремя.") from exc
        except (aiohttp.ClientError, ValueError) as exc:
            raise DgisError("Не удалось связаться с 2ГИС.") from exc
        meta = (data or {}).get("meta") or {}
        code = int(meta.get("code") or 0)
        if code == 404:
            break  # ничего не найдено (или страницы закончились)
        if code != 200:
            error = meta.get("error") or {}
            raise DgisError(f"2ГИС {code}: {error.get('message') or error.get('type') or 'ошибка'}"[:300])
        result = (data or {}).get("result") or {}
        page_items = result.get("items") or []
        items.extend(page_items)
        total = int(result.get("total") or 0)
        if not page_items or page * page_size >= total or (want and len(items) >= want):
            break
    if items and not any(item.get("contact_groups") for item in items) and not _warned_no_contacts:
        _warned_no_contacts = True
        log.warning("2ГИС не отдаёт телефоны: у ключа нет доступа к контактам (items.contact_groups).")
    return items
