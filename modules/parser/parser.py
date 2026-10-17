import asyncio
import html
import ipaddress
import math
import re
import socket
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import logging

import aiohttp
from selectolax.parser import HTMLParser

from . import analysis
from . import contacts as cn
from . import countries
from . import dgis
from . import geoapify
from . import google_places
from . import niches
from .config import (
    ANALYZE_SITES,
    DGIS_API_KEY,
    DGIS_MAX_PAGES,
    DGIS_PAGE_SIZE,
    GEOAPIFY_API_KEY,
    GOOGLE_MAX_PAGES,
    GOOGLE_PLACES_API_KEY,
    NOMINATIM_URL,
    OVERPASS_URL,
    USER_AGENT,
)
from .lead_identity import LeadIdentityIndex, claim_tokens, normalize_text, same_business

log = logging.getLogger("parser_cc.search")

OVERPASS_FALLBACK_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
# Сколько раз повторять запрос, если все зеркала перегружены (504/429), и пауза между кругами.
OVERPASS_ROUNDS = 3
OVERPASS_ROUND_PAUSE = 4.0
# Если Google/2ГИС уже дали достаточно бизнесов, OpenStreetMap ждём недолго — только чтобы
# подтвердить и дополнить данные, а не задерживать поиск из-за перегруженных серверов.
OSM_GRACE = 6.0

NICHES = niches.NICHES
FREE_HOSTS = analysis.FREE_HOSTS

_nominatim_lock = asyncio.Lock()
_last_nominatim_request = 0.0
_geocode_cache: dict[tuple[str, str], tuple[float, float, float, float]] = {}


class GeoError(Exception):
    pass


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Resolve only public IP addresses and return those exact answers to aiohttp."""

    def __init__(self):
        self._resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        records = await self._resolver.resolve(host, port, family)
        if not records:
            raise OSError("The host did not resolve to an IP address.")
        for record in records:
            address = ipaddress.ip_address(record["host"])
            if not address.is_global:
                raise OSError("Private or reserved network addresses are blocked.")
        return records

    async def close(self):
        await self._resolver.close()


async def geocode(
    session: aiohttp.ClientSession, city: str, country: str
) -> tuple[float, float, float, float]:
    global _last_nominatim_request
    cache_key = (city.strip().casefold(), country.lower())
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    # Nominatim asks applications to keep aggregate traffic at or below 1 r/s.
    async with _nominatim_lock:
        if cache_key in _geocode_cache:
            return _geocode_cache[cache_key]
        wait = 1.1 - (time.monotonic() - _last_nominatim_request)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_nominatim_request = time.monotonic()
        try:
            async with session.get(
                NOMINATIM_URL,
                params={
                    "q": city.strip(),
                    "countrycodes": country.lower(),
                    "format": "json",
                    "limit": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                if response.status != 200:
                    raise GeoError(f"Геокодер вернул HTTP {response.status}")
                data = await response.json(content_type=None)
        except asyncio.TimeoutError as exc:
            raise GeoError("Геокодер не ответил вовремя. Попробуйте позже.") from exc
        except aiohttp.ClientError as exc:
            raise GeoError("Не удалось связаться с геокодером.") from exc

    if not data:
        raise GeoError(f"Город «{city}» не найден в стране {country.upper()}.")
    try:
        box = data[0]["boundingbox"]  # south, north, west, east
        result = (float(box[0]), float(box[2]), float(box[1]), float(box[3]))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeoError("Геокодер вернул неполные координаты.") from exc
    _geocode_cache[cache_key] = result
    return result


def custom_term(custom: str) -> str:
    """Своя ниша: оставляем только буквы, цифры и пробелы, чтобы запрос был безопасным."""
    cleaned = re.sub(r"[^\w\s]", " ", custom.strip()[:80], flags=re.U).replace("_", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def first_letter_both_cases(pattern: str) -> str:
    """Overpass не всегда сравнивает кириллицу без учёта регистра, поэтому каждое слово
    дополнительно пишем как [Бб]арбер — находятся и «Барбершоп», и «барбершоп»."""
    parts = []
    for word in pattern.split("|"):
        head = word[:1]
        if head and head.lower() != head.upper():
            word = f"[{head.upper()}{head.lower()}]" + word[1:]
        parts.append(word)
    return "|".join(parts)


def build_query(
    bbox: tuple[float, float, float, float] | None,
    niche: int,
    custom: str,
    *,
    country: str = "",
    result_limit: int | None = None,
    require_phone: bool = False,
) -> str:
    country_area = bbox is None
    if country_area:
        country_code = country.upper()
        if not re.fullmatch(r"[A-Z]{2}", country_code):
            raise GeoError("Для поиска по стране нужен двухбуквенный код страны.")
        location = "(area.searchArea)"
        area_prelude = (
            f'area["ISO3166-1"="{country_code}"][admin_level=2]->.searchArea;\n'
        )
    else:
        south, west, north, east = bbox
        location = f"({south},{west},{north},{east})"
        area_prelude = ""
    clauses = []
    business = f'[~"^({niches.BUSINESS_KEYS})$"~"."]'
    # Быстрый режим выдаёт только бизнесы с телефоном — просим у Overpass сразу их,
    # ответ становится в разы меньше и приходит быстрее.
    phone = '[~"^(phone|contact:phone|mobile|contact:mobile)$"~"."]' if require_phone else ""
    if niche == niches.CUSTOM and custom.strip():
        term = custom_term(custom)
        if not term:
            raise GeoError("Слово для поиска должно содержать буквы или цифры.")
        clauses.append(f'nwr["name"~"{first_letter_both_cases(term)}",i]{business}{phone}{location};')
    else:
        spec = niches.get(niche)
        for flt in spec["osm"]:
            clauses.append(f"nwr{flt}{phone}{location};")
        if spec.get("name"):
            clauses.append(f'nwr["name"~"{first_letter_both_cases(spec["name"])}",i]{business}{phone}{location};')
    output = "out center tags;"
    if result_limit:
        output = f"out center tags {max(1, min(int(result_limit), 1500))};"
    return (
        "[out:json][timeout:50];\n"
        + area_prelude
        + "(\n"
        + "\n".join(clauses)
        + "\n);"
        + output
    )


# Кэш ответов Overpass: api.py подставляет сюда функции чтения/записи в базу.
# Одинаковый запрос (город + ниша) в течение нескольких дней отдаётся мгновенно.
CACHE_GET = None
CACHE_SET = None
OVERPASS_TIMEOUT = 55
OVERPASS_STAGGER = 1.2


class _Retryable(Exception):
    def __init__(self, status=None, timed_out=False):
        super().__init__(status)
        self.status = status
        self.timed_out = timed_out


async def _overpass_one(session, endpoint, query, delay):
    if delay:
        await asyncio.sleep(delay)
    try:
        async with session.post(
            endpoint,
            data={"data": query},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=OVERPASS_TIMEOUT),
        ) as response:
            if response.status != 200:
                if response.status in (406, 429) or response.status >= 500:
                    raise _Retryable(response.status)
                raise GeoError(
                    f"OpenStreetMap Overpass вернул HTTP {response.status}. "
                    "Проверьте параметры поиска."
                )
            try:
                data = await response.json(content_type=None)
            except (aiohttp.ClientError, ValueError) as exc:
                raise _Retryable() from exc
            if isinstance(data, dict) and isinstance(data.get("elements", []), list):
                if data.get("remark") and not data.get("elements"):
                    # «runtime error: timeout» и подобные — пустой ответ не считаем успехом
                    raise _Retryable()
                return data.get("elements", [])
            raise _Retryable()
    except asyncio.TimeoutError as exc:
        raise _Retryable(timed_out=True) from exc
    except aiohttp.ClientError as exc:
        raise _Retryable() from exc


async def overpass(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Несколько кругов запросов к зеркалам: карты часто перегружены на минуту‑другую,
    поэтому после неудачи ждём и пробуем снова, а не сдаёмся сразу."""
    last_error: GeoError | None = None
    for round_no in range(OVERPASS_ROUNDS):
        try:
            return await _overpass_round(session, query)
        except _HardGeoError as exc:
            raise GeoError(str(exc)) from exc
        except GeoError as exc:
            last_error = exc
            if round_no + 1 < OVERPASS_ROUNDS:
                await asyncio.sleep(OVERPASS_ROUND_PAUSE * (round_no + 1))
    raise last_error or GeoError("OpenStreetMap не ответил.")


class _HardGeoError(GeoError):
    """Ошибка в самом запросе (не перегрузка) — повторять бессмысленно."""


async def _overpass_round(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Запрос сразу к нескольким зеркалам Overpass (со сдвигом ~1 с): берём первый
    нормальный ответ, остальные отменяем. Раньше зеркала опрашивались по очереди
    с таймаутом 120 с, и один зависший сервер тормозил весь поиск."""
    if CACHE_GET is not None:
        try:
            cached = await CACHE_GET(query)
        except Exception:  # кэш не должен ломать поиск
            cached = None
        if cached is not None:
            return cached

    endpoints = list(dict.fromkeys((OVERPASS_URL, *OVERPASS_FALLBACK_URLS)))
    tasks = [
        asyncio.create_task(_overpass_one(session, url, query, i * OVERPASS_STAGGER))
        for i, url in enumerate(endpoints)
    ]
    last_status = None
    timed_out = False
    hard_error = None
    try:
        for finished in asyncio.as_completed(tasks):
            try:
                elements = await finished
            except _Retryable as exc:
                last_status = exc.status or last_status
                timed_out = timed_out or exc.timed_out
                continue
            except GeoError as exc:
                hard_error = exc
                continue
            if CACHE_SET is not None and elements:
                try:
                    await CACHE_SET(query, elements)
                except Exception:
                    pass
            return elements
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if hard_error is not None and last_status is None and not timed_out:
        raise _HardGeoError(str(hard_error))
    if last_status is not None:
        raise GeoError(
            "Сервис поиска OpenStreetMap временно недоступен "
            f"(HTTP {last_status}). Попробуйте позже."
        )
    if timed_out:
        raise GeoError("Поиск OpenStreetMap занял слишком много времени. Попробуйте позже.")
    raise GeoError("Не удалось получить корректный ответ от OpenStreetMap Overpass.")


def extract_contacts(tags: dict, country: str = "") -> dict:
    contacts = {}
    tg = cn.telegram(tags.get("contact:telegram") or tags.get("telegram"))
    if tg:
        contacts["tg"] = tg
    vk = cn.vk(tags.get("contact:vk") or tags.get("vk"))
    if vk:
        contacts["vkg" if vk.startswith(("club", "public", "event")) else "vk"] = vk
    wa = cn.whatsapp(tags.get("contact:whatsapp") or tags.get("whatsapp"), country)
    if wa:
        contacts["wa"] = wa
    vb = cn.viber(tags.get("contact:viber") or tags.get("viber"), country)
    if vb:
        contacts["vb"] = vb
    mail = cn.email(tags.get("contact:email") or tags.get("email"))
    if mail:
        contacts["email"] = mail
    ig = cn.instagram(tags.get("contact:instagram") or tags.get("instagram"))
    if ig:
        contacts["ig"] = ig
    fb = cn.facebook(tags.get("contact:facebook") or tags.get("facebook"))
    if fb:
        contacts["fb"] = fb

    street = " ".join(
        part for part in (
            tags.get("addr:street", "").strip(),
            tags.get("addr:housenumber", "").strip(),
        ) if part
    )
    locality = tags.get("addr:postcode", "").strip()
    if street:
        contacts["address"] = ", ".join(part for part in (street, locality) if part)
    return contacts


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw or raw.lower() in ("no", "none", "-"):
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or "." not in parsed.hostname
    ):
        return ""
    try:
        if parsed.port not in (None, 80, 443):
            return ""
        ascii_host = parsed.hostname.encode("idna").decode("ascii")
    except ValueError:
        return ""
    except UnicodeError:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9.-]+", ascii_host):
        return ""
    netloc = ascii_host
    if parsed.port:
        netloc += ":" + str(parsed.port)
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, parsed.fragment)
    )


class DNSFailure(Exception):
    pass


async def _public_address(hostname: str) -> bool:
    try:
        literal = ipaddress.ip_address(hostname)
        return literal.is_global
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise DNSFailure(hostname) from exc
    except (OSError, asyncio.TimeoutError):
        return False
    addresses = set()
    for record in records:
        try:
            addresses.add(ipaddress.ip_address(record[4][0]))
        except ValueError:
            return False
    # Reject a hostname if any DNS answer points to a local/reserved address.
    return bool(addresses) and all(address.is_global for address in addresses)


async def _checked_url(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    try:
        if parsed.port not in (None, 80, 443):
            return None
    except ValueError:
        return None
    if not await _public_address(parsed.hostname):
        return None
    return url


async def _fetch_public_page(
    session: aiohttp.ClientSession, start_url: str
) -> tuple[int, str, str, str]:
    url = start_url
    for _ in range(6):
        safe_url = await _checked_url(url)
        if not safe_url:
            raise ValueError("Сайт ведёт на непубличный или недопустимый адрес.")
        async with session.get(
            safe_url,
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=12),
            allow_redirects=False,
        ) as response:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    return response.status, "", str(response.url), ""
                url = urljoin(str(response.url), location)
                continue
            raw_body = await response.content.read(220_000)
            try:
                encoding = response.charset or "utf-8"
                body = raw_body.decode(encoding, "ignore")
            except LookupError:
                body = raw_body.decode("utf-8", "ignore")
            return (
                response.status,
                body,
                str(response.url),
                response.headers.get("Last-Modified", ""),
            )
    raise ValueError("Слишком много перенаправлений.")


def extract_site_contacts(body: str, page_url: str, country: str = "") -> dict:
    """Collect contact links that a business itself publishes on its home page."""
    result = {}
    tree = HTMLParser(body)

    for anchor in tree.css("a[href]"):
        href = html.unescape((anchor.attributes.get("href") or "").strip())
        lowered = href.lower()
        if lowered.startswith("mailto:"):
            address = cn.email(unquote(href[7:].split("?", 1)[0]))
            if address:
                result.setdefault("email", address)
            continue
        if lowered.startswith("tel:"):
            number = unquote(href[4:]).split(";", 1)[0].strip()
            if cn.phone(number, country)[0]:
                result.setdefault("phone", number)
            continue
        if lowered.startswith("viber://"):
            number = cn.viber(href, country)
            if number:
                result.setdefault("vb", number)
            continue
        if not lowered.startswith(("http://", "https://", "//")):
            continue
        try:
            absolute = urljoin(page_url, href)
            host = (urlsplit(absolute).hostname or "").lower()
        except ValueError:
            continue
        if host.startswith("www."):
            host = host[4:]
        if host in {"t.me", "telegram.me", "telegram.dog"}:
            value = cn.telegram(absolute)
            if value:
                result.setdefault("tg", value)
        elif host in {"wa.me", "api.whatsapp.com", "whatsapp.com"}:
            value = cn.whatsapp(absolute, country)
            if value:
                result.setdefault("wa", value)
        elif host in {"vk.com", "m.vk.com", "vk.ru", "m.vk.ru"}:
            value = cn.vk(absolute)
            if value and "vk" not in result and "vkg" not in result:
                result["vkg" if value.startswith(("club", "public", "event")) else "vk"] = value
        elif host in {"instagram.com", "m.instagram.com", "instagr.am"}:
            value = cn.instagram(absolute)
            if value:
                result.setdefault("ig", value)
        elif host in {"facebook.com", "m.facebook.com", "fb.com"}:
            value = cn.facebook(absolute)
            if value:
                result.setdefault("fb", value)

    if "email" not in result:
        text = html.unescape(tree.text()[:50000] if tree.body else "")
        address = cn.email(text)
        if address:
            result["email"] = address
    return result


# HTTP-ответы, которые чаще всего означают защиту от ботов, а не сломанный сайт.
UNVERIFIABLE_STATUSES = {401, 403, 405, 406, 409, 425, 429, 451, 503}


async def analyze_site(session: aiohttp.ClientSession, url: str, country: str = "") -> dict:
    """Открывает сайт и проверяет его. Результат:
    status: ok | weak | broken | unknown (unknown = не удалось проверить честно)."""
    result = {
        "status": "unknown", "final_url": url, "reasons": [], "contacts": {}, "checks": {},
    }
    started = time.perf_counter()
    try:
        status, body, final_url, last_modified = await _fetch_public_page(session, url)
    except DNSFailure:
        result.update(status="broken", final_url="", reasons=["домен сайта не существует или не настроен"])
        return result
    except asyncio.TimeoutError:
        result["reasons"] = ["сайт не ответил вовремя — не удалось проверить"]
        return result
    except ValueError:
        result.update(status="broken", final_url="", reasons=["адрес сайта недоступен"])
        return result
    except aiohttp.ClientSSLError:
        result.update(status="broken", reasons=["ошибка сертификата HTTPS — браузер покажет предупреждение"])
        return result
    except aiohttp.ClientConnectorError:
        result.update(status="broken", reasons=["сайт не открывается (сервер не отвечает)"])
        return result
    except (aiohttp.ClientError, OSError):
        result["reasons"] = ["соединение с сайтом оборвалось — не удалось проверить"]
        return result

    elapsed = time.perf_counter() - started
    result["final_url"] = final_url
    if status in UNVERIFIABLE_STATUSES:
        result["reasons"] = [f"сайт ограничивает автоматическую проверку (HTTP {status})"]
        return result
    if status >= 400:
        result.update(status="broken", reasons=[f"сайт отдаёт ошибку {status}"])
        return result

    checks = analysis.inspect_page(body, final_url, elapsed, last_modified)
    page_contacts = extract_site_contacts(body, final_url, country)
    has_reach = page_contacts.get("phone") or any(
        page_contacts.get(key) for key in ("tg", "wa", "vk", "vkg", "ig")
    )
    if not has_reach:
        contact_url = analysis.contact_page_url(checks["links"], final_url)
        if contact_url:
            try:
                c_status, c_body, c_final, _ = await _fetch_public_page(session, contact_url)
                if c_status < 400:
                    extra = extract_site_contacts(c_body, c_final, country)
                    for key, value in extra.items():
                        page_contacts.setdefault(key, value)
                    extra_checks = analysis.inspect_page(c_body, c_final, 0)
                    for key in ("tg", "tg_bot", "booking"):
                        if not checks[key] and extra_checks[key]:
                            checks[key] = extra_checks[key]
                    if not checks["form"] and extra_checks["form"]:
                        checks["form"] = True
                    checks["contact_page"] = c_final
            except (DNSFailure, ValueError, asyncio.TimeoutError, aiohttp.ClientError, OSError):
                pass
    problems = [
        problem for problem in checks["problems"]
        if not (problem == "на сайте не видно контактов" and (page_contacts or checks.get("contact_page")))
        and not (problem.startswith("нет онлайн-записи") and checks["booking"])
    ]
    checks.pop("links", None)
    checks["problems"] = problems
    if checks["tg_bot"]:
        page_contacts.setdefault("tg_bot", checks["tg_bot"])
    result.update(
        status="weak" if problems else "ok",
        reasons=problems,
        contacts=page_contacts,
        checks=checks,
    )
    return result


async def check_site(
    session: aiohttp.ClientSession, url: str, country: str = ""
) -> tuple[list[str], str, dict]:
    """Старый формат ответа (причины, итоговый адрес, контакты) — для совместимости."""
    found = await analyze_site(session, url, country)
    contacts = dict(found["contacts"])
    contacts.pop("tg_bot", None)
    reasons = found["reasons"] or ([] if found["status"] == "ok" else ["не удалось проверить"])
    return reasons, found["final_url"], contacts


def hot_score(site: str, reasons: list[str], phone: str, contacts: dict) -> int:
    lead = {"site": site, "reasons": reasons, "phone": phone, "contacts": contacts,
            "need": analysis.classify(site, reasons, False), "info": {}}
    return analysis.priority(lead)[0]


CLOSED_KEY_PREFIXES = ("disused:", "abandoned:", "was:", "demolished:", "removed:")


def _osm_is_closed(tags: dict) -> bool:
    if any(key.startswith(CLOSED_KEY_PREFIXES) for key in tags):
        return True
    if tags.get("shop") == "vacant" or tags.get("end_date"):
        return True
    hours = str(tags.get("opening_hours") or "").strip().lower()
    return hours in ("closed", "off")


def _osm_phone_raw(tags: dict) -> str:
    return (
        tags.get("phone")
        or tags.get("contact:phone")
        or tags.get("contact:mobile")
        or tags.get("mobile")
        or ""
    )


def osm_candidate(element: dict, country: str, city: str) -> dict | None:
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name or _osm_is_closed(tags):
        return None
    lat = element.get("lat", (element.get("center") or {}).get("lat"))
    lon = element.get("lon", (element.get("center") or {}).get("lon"))
    found = extract_contacts(tags, country)
    address = found.pop("address", "")
    key = f"{element.get('type', 'node')}/{element.get('id', '')}"
    return {
        "key": key,
        "source": "osm",
        "source_url": f"https://www.openstreetmap.org/{key}",
        "name": name,
        # Город показываем тот, в котором искали: в данных карт он бывает записан
        # на местном языке или как пригород.
        "city": city or tags.get("addr:city") or "",
        "phone_raw": _osm_phone_raw(tags),
        "url_raw": tags.get("website") or tags.get("contact:website") or tags.get("url") or "",
        "address": address,
        "map": cn.map_link(lat, lon, name, country),
        "lat": lat,
        "lon": lon,
        "tags": tags,
        "contacts": found,
        "country": country.upper(),
        "hours": str(tags.get("opening_hours") or "").strip()[:200],
    }


def _richness(candidate: dict) -> int:
    score = 0
    if candidate.get("phone_raw"):
        score += 10
    score += 4 * len(candidate.get("contacts") or {})
    if candidate.get("url_raw"):
        score += 3
    return score


async def _google_candidates(
    session: aiohttp.ClientSession,
    country: str,
    city: str,
    niche: int,
    custom: str,
    budget,
    bbox=None,
    want: int | None = None,
    seen_keys: set[str] | None = None,
) -> list[dict]:
    where = city or google_places.COUNTRY_NAMES.get(country.upper(), country.upper())
    found: list[dict] = []
    seen: set[str] = set(seen_keys or ())
    for query in google_places.queries_for(country, niche, custom):
        if want and len(found) >= want:
            break
        places = await google_places.text_search(
            session,
            GOOGLE_PLACES_API_KEY,
            f"{query} {where}".strip(),
            country,
            max_pages=GOOGLE_MAX_PAGES,
            on_request=budget,
            bbox=bbox,
            want=(want - len(found)) if want else None,
        )
        for place in places:
            candidate = google_places.to_candidate(place, country)
            if candidate and candidate["key"] not in seen:
                seen.add(candidate["key"])
                candidate["contacts"] = {}
                if not candidate["city"]:
                    candidate["city"] = city
                found.append(candidate)
    return found


async def _geoapify_candidates(session, country, city, niche, custom, bbox, limit, budget) -> list[dict]:
    if niche == niches.CUSTOM:
        return []  # Geoapify ищет по категориям, своя ниша идёт через OpenStreetMap.
    spec = niches.get(niche)
    if not spec.get("geoapify"):
        return []
    features = await geoapify.search(
        session, GEOAPIFY_API_KEY, spec["geoapify"], bbox, limit=limit, budget=budget
    )
    result = []
    for feature in features:
        candidate = geoapify.to_candidate(feature, country, city, spec.get("name_filter", ""))
        if not candidate:
            continue
        found = extract_contacts(candidate["tags"], country)
        found.pop("address", None)
        candidate["contacts"] = found
        result.append(candidate)
    return result


async def _dgis_candidates(session, country, city, niche, custom, bbox, budget, want=None) -> list[dict]:
    if not bbox or not dgis.covers(country):
        return []
    cis = country.upper() in google_places.CIS
    found: list[dict] = []
    seen: set[str] = set()
    for query in google_places.queries_for(country, niche, custom):
        if want and len(found) >= want:
            break
        items = await dgis.search(
            session, DGIS_API_KEY, query, bbox,
            max_pages=DGIS_MAX_PAGES, page_size=DGIS_PAGE_SIZE,
            want=(want - len(found)) if want else None,
            on_request=budget, locale="ru_RU" if cis else "en_AE",
        )
        for item in items:
            candidate = dgis.to_candidate(item, country, city)
            if candidate and candidate["key"] not in seen:
                seen.add(candidate["key"])
                if city:
                    candidate["city"] = city
                found.append(candidate)
    return found


def _source_title(source: str) -> str:
    return {"osm": "OpenStreetMap", "geoapify": "Geoapify (данные OpenStreetMap)",
            "google": "Google Maps", "dgis": "2ГИС"}.get(source, source)


SOURCE_BONUS = {"google": 4, "dgis": 4, "osm": 0, "geoapify": 0}


def _quality(candidate: dict) -> float:
    """Насколько полная карточка: телефон, рейтинг и отзывы, адрес, часы, сайт.
    Из одинаковых бизнесов в разных базах в выдачу идёт самый полный вариант."""
    score = float(_richness(candidate))
    if candidate.get("rating"):
        score += 4
    score += min(int(candidate.get("reviews") or 0), 300) / 30
    if candidate.get("address"):
        score += 4
    if candidate.get("hours"):
        score += 2
    score += SOURCE_BONUS.get(candidate.get("source", ""), 0)
    score += 6 * (len(candidate.get("also") or ()))
    return score


def _merge_into(winner: dict, other: dict) -> None:
    """Дополняет лучшую карточку данными той же организации из другой базы."""
    if other.get("phone_raw"):
        phones = [part for part in (winner.get("phone_raw") or "").split(";") if part]
        for part in str(other["phone_raw"]).split(";"):
            if part and part not in phones:
                phones.append(part)
        winner["phone_raw"] = ";".join(phones)
    for field in ("url_raw", "address", "hours", "map", "lat", "lon"):
        if not winner.get(field) and other.get(field):
            winner[field] = other[field]
    if other.get("rating") and (other.get("reviews") or 0) > (winner.get("reviews") or 0):
        winner["rating"], winner["reviews"] = other["rating"], other.get("reviews")
    contacts = dict(winner.get("contacts") or {})
    for key, value in (other.get("contacts") or {}).items():
        contacts.setdefault(key, value)
    winner["contacts"] = contacts
    also = winner.setdefault("also", [])
    if other.get("source") != winner.get("source") and all(item["source"] != other.get("source") for item in also):
        also.append({"source": other.get("source", ""),
                     "url": other.get("source_url") or other.get("map") or ""})


def _distance_m(a: dict, b: dict) -> float | None:
    try:
        lat1, lon1, lat2, lon2 = (float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    dy = (lat2 - lat1) * 111_320
    dx = (lon2 - lon1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _same_place(group: list, candidate: dict, identity: dict) -> bool:
    """Та же организация в другой базе: совпадает по признакам или стоит в той же точке
    (до 300 м) с тем же телефоном или похожим названием."""
    if same_business(group[1], identity):
        return True
    distance = _distance_m(group[0], candidate)
    if distance is None or distance > 300:
        return False
    if identity.get("phone") and identity["phone"] == group[1].get("phone"):
        return True
    left, right = normalize_text(group[0].get("name")), normalize_text(candidate.get("name"))
    return bool(left and right and (left in right or right in left))


def _identity(candidate: dict, country: str, city: str = "") -> dict:
    """Признаки бизнеса для склейки и закрепления — те же, что потом проверит claim_leads:
    все телефоны карточки, сайт, соцсети, адрес и координаты."""
    found_phones = cn.phones(candidate.get("phone_raw"), country)
    found_contacts = dict(candidate.get("contacts") or {})
    if candidate.get("address"):
        found_contacts["address"] = candidate["address"]
    return {
        "osm_key": candidate["key"],
        "name": candidate["name"],
        "country": country,
        "city": candidate.get("city") or city,
        "phone": found_phones[0][0] if found_phones else "",
        "site_url": normalize_url(candidate.get("url_raw") or ""),
        "lat": candidate.get("lat"),
        "lon": candidate.get("lon"),
        "contacts": found_contacts,
        "info": {"phones_e164": [e164 for e164, _pretty in found_phones]},
    }


def _sources_info(candidate: dict) -> list[dict]:
    items = [{"t": _source_title(candidate["source"]),
              "u": candidate.get("source_url") or candidate.get("map") or ""}]
    for extra in candidate.get("also") or ():
        items.append({"t": _source_title(extra["source"]), "u": extra.get("url") or ""})
    return [item for item in items if item["u"]]


MODE_SITES = {
    "none": {"none", "broken"},
    "weak": {"weak"},
    "both": {"none", "broken", "weak"},
    "bot": {"ok"},
    "all": {"none", "broken", "weak", "ok"},
}


async def _report(callback, *args) -> None:
    if callback is None:
        return
    try:
        await callback(*args)
    except Exception:
        log.exception("Search callback failed")


async def run_search(
    country: str,
    city: str,
    niche: int,
    custom: str,
    mode: str,
    count: int,
    progress=None,
    exclude_keys: set[str] | None = None,
    exclude_leads: list[dict] | None = None,
    google_budget=None,
    *,
    dgis_budget=None,
    exclude_tokens: set[str] | None = None,
    geo_budget=None,
    on_source_error=None,
    on_analyzed=None,
    analyze: bool | None = None,
) -> list[dict]:
    """Ищет организации. mode: none (нет сайта), weak (слабый сайт), both (нет или слабый),
    bot (нормальный сайт без бота) или all.

    Источники изолированы: если один не работает, поиск продолжается по остальным.
    В выдачу попадают только проверенные организации, с которыми можно связаться,
    которых нет у других пользователей (exclude_tokens) и которые подходят под режим."""
    country = country.upper()
    if analyze is None:
        analyze = ANALYZE_SITES
    # Без проверки сайтов выдаём все найденные бизнесы: участник сам смотрит карточку на карте.
    allowed_sites = MODE_SITES.get(mode, MODE_SITES["both"]) if analyze else MODE_SITES["all"]
    taken = set() if callable(exclude_tokens) else set(exclude_tokens or ())
    checked = 0
    connector = aiohttp.TCPConnector(limit=12, resolver=PublicResolver())
    timeout = aiohttp.ClientTimeout(total=150)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        city = city.strip()
        candidates: list[dict] = []
        failures: list[str] = []

        need_more = count * 3
        # Без города обходим несколько городов и набираем запас побольше.
        target = need_more if city else need_more * 2
        known_keys: set[str] = set()

        def add(items: list[dict]) -> None:
            for item in items:
                if item["key"] not in known_keys:
                    known_keys.add(item["key"])
                    candidates.append(item)

        async def free_count() -> int:
            """Сколько собранных бизнесов с телефоном реально можно выдать: не у этого
            участника и не закреплены за другими."""
            pool = [
                item for item in candidates
                if item.get("phone_raw") and not (exclude_keys and item["key"] in exclude_keys)
            ]
            token_sets = [claim_tokens(_identity(item, country, city)) for item in pool]
            if callable(exclude_tokens):
                busy = await exclude_tokens(set().union(*token_sets)) if token_sets else set()
            else:
                busy = set(exclude_tokens or ())
            return sum(1 for tokens in token_sets if not (tokens & busy))

        def useful_count() -> int:
            return sum(
                1 for item in candidates
                if not (exclude_keys and item["key"] in exclude_keys)
                and (item.get("phone_raw") or item.get("contacts"))
            )

        async def collect_area(area_city: str, bbox) -> None:
            """Собирает организации одного города (или всей страны, если bbox=None) сразу
            из всех подключённых баз: Google Places и 2ГИС (если есть ключи) и OpenStreetMap.
            Одинаковые бизнесы потом склеиваются, и в выдачу идёт самая полная карточка."""

            async def from_google() -> None:
                if not (GOOGLE_PLACES_API_KEY and useful_count() < target):
                    return
                try:
                    add(
                        await _google_candidates(
                            session, country, area_city, niche, custom, google_budget,
                            bbox=bbox, want=max(10, target - useful_count()),
                            seen_keys=set(known_keys),
                        )
                    )
                except google_places.GoogleError as exc:
                    failures.append("google")
                    log.warning("Google Places: %s", exc)
                    await _report(on_source_error, "google", str(exc))

            async def from_dgis() -> None:
                if not (DGIS_API_KEY and useful_count() < target):
                    return
                try:
                    add(
                        await _dgis_candidates(
                            session, country, area_city, niche, custom, bbox, dgis_budget,
                            want=max(10, target - useful_count()),
                        )
                    )
                except dgis.DgisError as exc:
                    failures.append("dgis")
                    log.warning("2ГИС: %s", exc)
                    await _report(on_source_error, "dgis", str(exc))

            async def from_osm() -> None:
                result_limit = min(1500, max(500, count * 10 + 100))
                try:
                    query = build_query(
                        bbox, niche, custom, country=country, result_limit=result_limit,
                        require_phone=not analyze,
                    )
                    elements = await overpass(session, query)
                    osm = [
                        candidate for candidate in (
                            osm_candidate(element, country, area_city) for element in elements
                        ) if candidate
                    ]
                    osm.sort(key=lambda item: (-_richness(item), -len(item["tags"])))
                    add(osm)
                except GeoError as exc:
                    if niche == niches.CUSTOM and "буквы или цифры" in str(exc):
                        raise
                    failures.append("osm")
                    log.warning("Overpass (%s): %s", area_city or country, exc)
                    await _report(on_source_error, "osm", f"{area_city or country}: {exc}")

            osm_task = asyncio.create_task(from_osm())
            try:
                if GOOGLE_PLACES_API_KEY or DGIS_API_KEY:
                    await asyncio.gather(from_google(), from_dgis())
                    if not osm_task.done() and useful_count() >= target and await free_count() >= target:
                        # Google/2ГИС хватило — OpenStreetMap не ждём дольше нескольких секунд.
                        await asyncio.wait({osm_task}, timeout=OSM_GRACE)
                        if not osm_task.done():
                            osm_task.cancel()
                (osm_result,) = await asyncio.gather(osm_task, return_exceptions=True)
            finally:
                if not osm_task.done():
                    osm_task.cancel()
            if isinstance(osm_result, Exception):
                raise osm_result
            if GEOAPIFY_API_KEY and bbox and useful_count() < target:
                try:
                    add(
                        await _geoapify_candidates(
                            session, country, area_city, niche, custom, bbox,
                            min(500, max(200, count * 8)), geo_budget,
                        )
                    )
                except geoapify.SourceError as exc:
                    failures.append("geoapify")
                    log.warning("Geoapify: %s", exc)
                    await _report(on_source_error, "geoapify", str(exc))

        async def area_bbox(area_city: str):
            """Координаты известных городов лежат в cities.json — без геокодера и ожидания.
            Неизвестное название (старые клиенты, свой ввод) ищем через Nominatim."""
            box = countries.city_bbox(country, area_city)
            if box:
                return box, True
            return await geocode(session, area_city, country), False

        async def report_collected() -> None:
            # Пока идёт сбор с карт, показываем осторожную оценку: половину найденных
            # бизнесов с телефоном (часть потом отсеется как уже выданные другим).
            if progress:
                with_phone = sum(
                    1 for item in candidates
                    if item.get("phone_raw") and not (exclude_keys and item["key"] in exclude_keys)
                )
                try:
                    await progress(min(count, with_phone // 2), len(candidates))
                except Exception:
                    log.exception("progress callback failed")

        async def collect_with_widen(area_city: str) -> None:
            box, from_point = await area_bbox(area_city)
            before = useful_count()
            await collect_area(area_city, box)
            await report_collected()
            if from_point and useful_count() - before < count:
                # мало бизнесов в центре — один раз расширяем район (пригороды, агломерация)
                wide = countries.city_bbox(country, area_city, scale=2.2)
                if wide:
                    await collect_area(area_city, wide)
                    await report_collected()

        if city:
            if useful_count() < need_more:
                await collect_with_widen(city)  # город не найден → понятная ошибка
        else:
            # Без города: обходим крупные города страны парами (параллельно), пока не наберём запас.
            order = countries.search_order(country)
            visited = 0
            index = 0
            while index < len(order):
                if useful_count() >= need_more * 2 or visited >= countries.MAX_CITIES_PER_SEARCH:
                    break
                batch = order[index:index + 2]
                index += len(batch)
                results = await asyncio.gather(
                    *(collect_with_widen(area_city) for area_city in batch),
                    return_exceptions=True,
                )
                for area_city, result in zip(batch, results):
                    if isinstance(result, GeoError):
                        await _report(on_source_error, "geocoder", f"{area_city}: {result}")
                    elif isinstance(result, BaseException):
                        raise result
                    else:
                        visited += 1
            if not order:
                await collect_area("", None)

        if not candidates and failures:
            raise GeoError(
                "Источники данных сейчас недоступны. Попробуйте через несколько минут."
            )

        prepared = []
        for candidate in candidates:
            if exclude_keys and candidate["key"] in exclude_keys:
                continue
            site_url = normalize_url(candidate["url_raw"])
            e164, pretty = cn.phone(candidate["phone_raw"], country)
            found_contacts = dict(candidate.get("contacts") or {})
            if not (e164 or site_url or cn.has_reachable_contact("", found_contacts)):
                continue
            if not analyze and not (e164 and candidate.get("map")):
                continue  # нужен телефон из карточки и ссылка на карту
            identity = _identity(candidate, country, city)
            prepared.append((candidate, identity, pretty, claim_tokens(identity)))

        # Бизнесы, которые уже выданы кому-то или в чёрном списке, сразу отбрасываем.
        if callable(exclude_tokens):
            all_tokens = set().union(*(item[3] for item in prepared)) if prepared else set()
            taken = await exclude_tokens(all_tokens)

        # Один и тот же бизнес часто есть сразу в нескольких базах. Склеиваем такие карточки
        # (общий телефон, сайт, название с адресом или координатами) и оставляем самую полную,
        # дополнив её телефонами, рейтингом и адресом из остальных баз.
        own_index = LeadIdentityIndex(exclude_leads or [])
        prepared.sort(key=lambda item: -_quality(item[0]))
        groups: list[list] = []
        token_group: dict[str, list] = {}
        for candidate, identity, pretty, tokens in prepared:
            if taken and tokens & taken:
                continue
            if own_index.find_duplicate(identity):
                continue  # уже есть в лидах у этого участника
            group = next((token_group[token] for token in tokens if token in token_group), None)
            if group is None:
                group = [candidate, identity, pretty, set(tokens)]
                groups.append(group)
            elif _same_place(group, candidate, identity):
                _merge_into(group[0], candidate)
                group[3] |= tokens
            else:
                # Общий телефон или сайт у разных точек (филиалы сети): такой бизнес всё равно
                # закрепляется за одним участником, поэтому берём только лучшую карточку.
                group[3] |= tokens
            for token in tokens:
                token_group.setdefault(token, group)

        groups.sort(key=lambda group: -_quality(group[0]))
        unique_candidates = []
        candidate_limit = count * 6 + 40
        for candidate, _identity_old, pretty, _tokens in groups[:candidate_limit]:
            # После склейки признаки пересчитываем: добавились телефоны, адрес и контакты.
            merged_phones = cn.phones(candidate["phone_raw"], country)
            if merged_phones:
                pretty = merged_phones[0][1]
            unique_candidates.append((candidate, _identity(candidate, country, city), pretty))

        semaphore = asyncio.Semaphore(8)
        telegram = analysis.TelegramChecker(session)
        social = analysis.SocialChecker(session)
        results = []
        result_lock = asyncio.Lock()
        result_index = LeadIdentityIndex(exclude_leads or [])
        issued_tokens: set[str] = set()

        def claimable(lead: dict) -> bool:
            """Тот же контроль, что в claim_leads: лид не должен делить телефон, сайт или
            соцсеть с уже выбранными или чужими лидами — иначе он потеряется при сохранении."""
            tokens = claim_tokens(lead)
            if not tokens or tokens & issued_tokens or (taken and tokens & taken):
                return False
            issued_tokens.update(tokens)
            return True

        niche_title = niches.title(niche, custom)

        async def quick(candidate, identity):
            """Быстрый режим: телефон(ы) и карточка на карте, без проверки сайта и соцсетей."""
            nonlocal checked
            found_phones = cn.phones(candidate["phone_raw"], country)
            info = {
                "niche": niche_title,
                "address": candidate.get("address") or "",
                "hours": candidate.get("hours") or "",
                "phones": [pretty for _e164, pretty in found_phones],
                "phones_e164": [e164 for e164, _pretty in found_phones],
                "lat": candidate.get("lat"),
                "lon": candidate.get("lon"),
                "rating": candidate.get("rating"),
                "reviews": candidate.get("reviews"),
                "sources": _sources_info(candidate),
            }
            lead_contacts = {"map": candidate["map"]}
            if candidate.get("address"):
                lead_contacts["address"] = candidate["address"]
            lead = {
                "osm_key": candidate["key"],
                "name": candidate["name"],
                "country": country,
                "city": candidate["city"] or city or "Не указан",
                "phone": found_phones[0][1] if found_phones else "",
                "phone_e164": found_phones[0][0] if found_phones else "",
                "site": "unchecked",
                "site_url": "",
                "reasons": [],
                "contacts": lead_contacts,
                "need": "",
                "info": info,
                "source": candidate["source"],
                "lat": candidate.get("lat"),
                "lon": candidate.get("lon"),
                "explain": "",
            }
            lead["hot"] = min(100, 40 + 15 * bool(info["address"]) + 15 * bool(info["hours"])
                              + 5 * min(len(found_phones), 3) + 10
                              + 5 * bool(info["rating"]) + 5 * min(len(candidate.get("also") or ()), 2))
            async with result_lock:
                checked += 1
                duplicate = result_index.find_duplicate(identity)
                if duplicate is None:
                    result_index.add(identity)
                    if found_phones and len(results) < count and claimable(lead):
                        results.append(lead)
                if progress:
                    await progress(len(results), checked)

        async def handle(candidate, identity, pretty):
            nonlocal checked
            if not analyze:
                await quick(candidate, identity)
                return
            url = identity["site_url"]
            lead_contacts = dict(identity["contacts"])
            phone_e164, phone_pretty = identity["phone"], pretty
            unknown = 0

            async with semaphore:
                if not url:
                    site_info = {"status": "none", "final_url": "", "reasons": ["сайта нет"],
                                 "contacts": {}, "checks": {}}
                else:
                    site_info = await analyze_site(session, url, country)
            site = site_info["status"]
            if site == "unknown":
                unknown += 2
            page_contacts = dict(site_info["contacts"])
            if not phone_e164 and page_contacts.get("phone"):
                phone_e164, phone_pretty = cn.phone(page_contacts["phone"], country)
            page_contacts.pop("phone", None)
            tg_bot = page_contacts.pop("tg_bot", "")
            for key, value in page_contacts.items():
                if key in ("vk", "vkg") and (lead_contacts.get("vk") or lead_contacts.get("vkg")):
                    continue
                lead_contacts.setdefault(key, value)
            if lead_contacts.get("tg") and analysis.is_bot_name(lead_contacts["tg"]):
                tg_bot = tg_bot or lead_contacts["tg"]
            if lead_contacts.get("tg"):
                exists = await telegram.exists(lead_contacts["tg"])
                if exists is False:
                    dead = lead_contacts.pop("tg")  # ссылка не открывается — не показываем
                    if tg_bot and tg_bot.lower() == dead.lower():
                        tg_bot = ""
                elif exists is None:
                    unknown += 1
            if tg_bot and tg_bot.lower() != str(lead_contacts.get("tg", "")).lower():
                if await telegram.exists(tg_bot) is False:
                    tg_bot = ""
            # Страницы ВК и Instagram из карт бывают удалены — неработающие не показываем.
            for social_key, kind in (("vk", "vk"), ("vkg", "vk"), ("ig", "ig")):
                if lead_contacts.get(social_key):
                    if await social.exists(kind, lead_contacts[social_key]) is False:
                        lead_contacts.pop(social_key)
            if candidate.get("map"):
                lead_contacts["map"] = candidate["map"]

            identity.update(
                {"phone": phone_e164, "site_url": site_info["final_url"] or url, "contacts": lead_contacts}
            )
            checks = site_info.get("checks") or {}
            info = {
                "niche": niche_title,
                "address": candidate.get("address") or "",
                "hours": candidate.get("hours") or "",
                "rating": candidate.get("rating"),
                "reviews": candidate.get("reviews"),
                "tg_bot": tg_bot,
                "booking": checks.get("booking", ""),
                "form": checks.get("form"),
                "https": checks.get("https"),
                "mobile": checks.get("mobile"),
                "speed": checks.get("speed"),
                "actual": checks.get("actual"),
                "year": checks.get("year"),
                "reservation": checks.get("reservation"),
                "unknown": unknown,
                "lat": candidate.get("lat"),
                "lon": candidate.get("lon"),
                "sources": _sources_info(candidate),
            }
            need = analysis.classify(site, site_info["reasons"], bool(tg_bot))
            reachable = cn.has_reachable_contact(phone_e164, lead_contacts)
            lead = {
                "osm_key": candidate["key"],
                "name": candidate["name"],
                "country": country,
                "city": candidate["city"] or city or "Не указан",
                "phone": phone_pretty,
                "phone_e164": phone_e164,
                "site": site,
                "site_url": site_info["final_url"] if site in ("weak", "ok", "broken") else "",
                "reasons": site_info["reasons"],
                "contacts": lead_contacts,
                "need": need,
                "info": info,
                "source": candidate["source"],
                "lat": candidate.get("lat"),
                "lon": candidate.get("lon"),
            }
            if site in ("weak", "ok") and site_info["final_url"]:
                lead_contacts["site"] = site_info["final_url"]
            lead["hot"], lead["explain"] = analysis.priority(lead)

            async with result_lock:
                checked += 1
                verified = unknown < 2 and site != "unknown"
                if verified and reachable:
                    await _report(on_analyzed, lead)
                duplicate = result_index.find_duplicate(identity)
                if duplicate is None:
                    result_index.add(identity)
                keep = site in allowed_sites and bool(need)
                if (duplicate is None and keep and reachable and verified and len(results) < count
                        and claimable(lead)):
                    results.append(lead)
                if progress:
                    await progress(len(results), checked)

        tasks = [
            asyncio.create_task(handle(*candidate))
            for candidate in unique_candidates
        ]
        try:
            for task in asyncio.as_completed(tasks):
                await task
                if len(results) >= count:
                    break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        output = sorted(results, key=lambda item: -item["hot"])[:count]
    return output
