"""Поиск организаций через Google Places API (New), Text Search."""

from __future__ import annotations

import asyncio

import aiohttp

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.shortFormattedAddress",
        "places.addressComponents",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.regularOpeningHours.weekdayDescriptions",
        "nextPageToken",
    )
)

CIS = {"RU", "BY", "KZ", "UZ", "KG", "TJ", "AM", "AZ", "UA", "GE", "MD"}
COUNTRY_NAMES = {
    "RU": "Россия", "UA": "Украина", "BY": "Беларусь", "KZ": "Казахстан",
    "PL": "Polska", "UZ": "Oʻzbekiston", "GE": "Georgia", "LT": "Lietuva",
    "DE": "Deutschland", "AE": "United Arab Emirates", "KG": "Кыргызстан",
    "AM": "Армения", "AZ": "Азербайджан", "MD": "Молдова",
}


class GoogleError(Exception):
    pass


def queries_for(country: str, niche: int, custom: str) -> list[str]:
    from . import niches

    if niche == niches.CUSTOM and custom.strip():
        return [custom.strip()[:80]]
    spec = niches.get(niche)
    return list(spec["google_ru"] if country.upper() in CIS else spec["google_en"])


def _locality(place: dict) -> str:
    for component in place.get("addressComponents") or []:
        if "locality" in (component.get("types") or []):
            return component.get("longText") or component.get("shortText") or ""
    return ""


def to_candidate(place: dict, country: str) -> dict | None:
    place_id = place.get("id")
    name = ((place.get("displayName") or {}).get("text") or "").strip()
    if not place_id or not name:
        return None
    status = place.get("businessStatus")
    if status and status != "OPERATIONAL":
        return None
    location = place.get("location") or {}
    return {
        "key": "g:" + place_id,
        "source": "google",
        "name": name,
        "city": _locality(place),
        "phone_raw": place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or "",
        "url_raw": place.get("websiteUri") or "",
        "address": place.get("shortFormattedAddress") or place.get("formattedAddress") or "",
        "map": place.get("googleMapsUri") or "",
        "lat": location.get("latitude"),
        "lon": location.get("longitude"),
        "tags": {},
        "country": country.upper(),
        "source_url": place.get("googleMapsUri") or "",
        "rating": place.get("rating"),
        "reviews": place.get("userRatingCount"),
        "hours": "; ".join(((place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [])[:7])[:300],
    }


async def text_search(
    session: aiohttp.ClientSession,
    api_key: str,
    text: str,
    country: str,
    *,
    max_pages: int = 3,
    on_request=None,
    bbox: tuple[float, float, float, float] | None = None,
    want: int | None = None,
) -> list[dict]:
    """Возвращает места по запросу. on_request() вызывается перед каждым платным запросом
    и должен вернуть False, если лимит запросов исчерпан."""
    places: list[dict] = []
    page_token = ""
    for _ in range(max(1, max_pages)):
        if on_request is not None and not await on_request():
            break
        body = {
            "textQuery": text,
            "languageCode": "ru",
            "regionCode": country.upper(),
            "pageSize": 20,
        }
        if bbox:
            south, west, north, east = bbox
            body["locationRestriction"] = {"rectangle": {
                "low": {"latitude": south, "longitude": west},
                "high": {"latitude": north, "longitude": east},
            }}
        if page_token:
            body["pageToken"] = page_token
        try:
            async with session.post(
                SEARCH_URL,
                json=body,
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200:
                    message = ""
                    if isinstance(data, dict):
                        message = (data.get("error") or {}).get("message", "")
                    raise GoogleError(f"Google Places HTTP {response.status}: {message}"[:300])
        except asyncio.TimeoutError as exc:
            raise GoogleError("Google Places не ответил вовремя.") from exc
        except aiohttp.ClientError as exc:
            raise GoogleError("Не удалось связаться с Google Places.") from exc
        places.extend((data or {}).get("places") or [])
        page_token = (data or {}).get("nextPageToken") or ""
        if not page_token or (want and len(places) >= want):
            break
    return places
