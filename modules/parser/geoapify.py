"""Источник Geoapify Places (бесплатный тариф, ключ без банковской карты).

Адаптер изолирован: любая ошибка превращается в SourceError и не ломает поиск,
остальные источники продолжают работать."""

from __future__ import annotations

import asyncio
import math
import re

import aiohttp

from . import contacts as cn

PLACES_URL = "https://api.geoapify.com/v2/places"
PAGE_SIZE = 100


class SourceError(Exception):
    pass


def credits_for(limit: int) -> int:
    """Geoapify списывает кредит за каждые 20 мест в ответе. Считаем с запасом."""
    return max(1, math.ceil(limit / 20))


def _tags(props: dict) -> dict:
    """Собирает теги в формате OSM: исходные теги источника + поля Geoapify."""
    raw = ((props.get("datasource") or {}).get("raw") or {})
    tags = {str(key): str(value) for key, value in raw.items() if isinstance(value, (str, int, float))}
    contact = props.get("contact") or {}
    if props.get("website") and not tags.get("website"):
        tags["website"] = str(props["website"])
    if contact.get("phone") and not (tags.get("phone") or tags.get("contact:phone")):
        tags["phone"] = str(contact["phone"])
    if contact.get("email") and not (tags.get("email") or tags.get("contact:email")):
        tags["email"] = str(contact["email"])
    if props.get("opening_hours") and not tags.get("opening_hours"):
        tags["opening_hours"] = str(props["opening_hours"])
    if props.get("street") and not tags.get("addr:street"):
        tags["addr:street"] = str(props["street"])
    if props.get("housenumber") and not tags.get("addr:housenumber"):
        tags["addr:housenumber"] = str(props["housenumber"])
    if props.get("city") and not tags.get("addr:city"):
        tags["addr:city"] = str(props["city"])
    if props.get("name") and not tags.get("name"):
        tags["name"] = str(props["name"])
    return tags


def to_candidate(feature: dict, country: str, city: str, name_filter: str = "") -> dict | None:
    props = feature.get("properties") or {}
    name = str(props.get("name") or "").strip()
    if not name:
        return None
    if name_filter and not re.search(name_filter, name, re.I):
        return None
    feature_country = str(props.get("country_code") or "").upper()
    if feature_country and country and feature_country != country.upper():
        return None
    tags = _tags(props)
    raw = ((props.get("datasource") or {}).get("raw") or {})
    osm_id = raw.get("osm_id")
    osm_type = {"n": "node", "w": "way", "r": "relation"}.get(str(raw.get("osm_type") or "")[:1])
    if osm_id and osm_type:
        key = f"{osm_type}/{abs(int(osm_id))}"
        source_url = f"https://www.openstreetmap.org/{key}"
    else:
        key = "geo:" + str(props.get("place_id") or "")
        source_url = ""
    if key == "geo:":
        return None
    lat, lon = props.get("lat"), props.get("lon")
    return {
        "key": key,
        "source": "geoapify",
        "source_url": source_url,
        "name": name,
        # Город показываем тот, в котором искали: в данных карт он бывает записан
        # на местном языке или как пригород.
        "city": city or tags.get("addr:city") or "",
        "phone_raw": tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or "",
        "url_raw": tags.get("website") or tags.get("contact:website") or "",
        "address": str(props.get("address_line2") or props.get("formatted") or "").strip(),
        "map": cn.map_link(lat, lon, name, country),
        "lat": lat,
        "lon": lon,
        "tags": tags,
        "country": country.upper(),
        "hours": tags.get("opening_hours", ""),
    }


async def search(
    session: aiohttp.ClientSession,
    api_key: str,
    categories: list[str],
    bbox: tuple[float, float, float, float],
    *,
    limit: int = 300,
    budget=None,
) -> list[dict]:
    """bbox: (south, west, north, east). budget(credits) -> bool, False = лимит исчерпан."""
    south, west, north, east = bbox
    features: list[dict] = []
    offset = 0
    while offset < limit:
        page = min(PAGE_SIZE, limit - offset)
        if budget is not None and not await budget(credits_for(page)):
            break
        params = {
            "categories": ",".join(categories),
            "filter": f"rect:{west},{north},{east},{south}",
            "limit": str(page),
            "offset": str(offset),
            "lang": "ru",
            "apiKey": api_key,
        }
        try:
            async with session.get(
                PLACES_URL, params=params, timeout=aiohttp.ClientTimeout(total=25)
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200:
                    message = ""
                    if isinstance(data, dict):
                        message = str(data.get("message") or data.get("error") or "")
                    raise SourceError(f"Geoapify HTTP {response.status}: {message}"[:300])
        except asyncio.TimeoutError as exc:
            raise SourceError("Geoapify не ответил вовремя.") from exc
        except aiohttp.ClientError as exc:
            raise SourceError("Не удалось связаться с Geoapify.") from exc
        except ValueError as exc:
            raise SourceError("Geoapify вернул некорректный ответ.") from exc
        batch = (data or {}).get("features") or []
        features.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return features
