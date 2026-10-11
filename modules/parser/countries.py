"""Страны и города для поиска.

Список городов с координатами и населением лежит в cities.json (выгрузка из
OpenStreetMap: от самых крупных к самым маленьким, 60–150 на страну). Благодаря
координатам поиск не ждёт геокодер (Nominatim — не чаще 1 запроса в секунду) и
сразу запрашивает организации в районе города.

Если город не указан, парсер обходит крупные города страны по очереди
(каждый раз начиная с другого), а не одним огромным запросом по всей стране."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

TITLES = {
    "RU": "Россия", "UA": "Украина", "BY": "Беларусь", "KZ": "Казахстан",
    "UZ": "Узбекистан", "KG": "Кыргызстан", "AM": "Армения", "AZ": "Азербайджан",
    "GE": "Грузия", "MD": "Молдова", "PL": "Польша", "LT": "Литва",
    "DE": "Германия", "AE": "ОАЭ",
}

ORDER = ["RU", "UA", "BY", "KZ", "UZ", "KG", "AM", "AZ", "GE", "MD", "PL", "LT", "DE", "AE"]

# Сколько городов максимум обходить за один поиск без указанного города.
MAX_CITIES_PER_SEARCH = 4
# Без города ищем только среди самых крупных: в деревнях бизнесов почти нет.
AUTO_CITIES = 15

_DATA_FILE = Path(__file__).with_name("cities.json")


def _load() -> dict[str, list[dict]]:
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    data: dict[str, list[dict]] = {}
    for code in ORDER:
        items = []
        for row in raw.get(code, []):
            # [название по-русски, местное название, широта, долгота, население]
            try:
                name, local, lat, lon, population = row[:5]
                items.append({
                    "name": str(name), "local": str(local or ""),
                    "lat": float(lat), "lon": float(lon), "population": int(population or 0),
                })
            except (TypeError, ValueError):
                continue
        data[code] = items
    return data


_CITIES = _load()


def _key(text: str) -> str:
    return " ".join((text or "").replace("ё", "е").replace("Ё", "Е").casefold().split())


_INDEX: dict[str, dict[str, dict]] = {}
for _code, _items in _CITIES.items():
    index: dict[str, dict] = {}
    for _item in _items:
        for _name in (_item["name"], _item["local"]):
            if _name:
                index.setdefault(_key(_name), _item)
    _INDEX[_code] = index

# Совместимость: раньше города хранились латиницей / без «ё».
_ALIASES = {
    "киев": "Киев", "kyiv": "Киев", "kiev": "Киев", "кишинев": "Кишинёв",
    "warsaw": "Варшава", "munich": "Мюнхен", "cologne": "Кёльн",
}

COUNTRIES: dict[str, dict] = {
    code: {"title": TITLES[code], "cities": [item["name"] for item in _CITIES.get(code, [])]}
    for code in ORDER
}


def cities(country: str) -> list[str]:
    return list(COUNTRIES.get(country.upper(), {}).get("cities", []))


def find(country: str, city: str) -> dict | None:
    index = _INDEX.get((country or "").upper(), {})
    key = _key(city)
    item = index.get(key)
    if item is None and key in _ALIASES:
        item = index.get(_key(_ALIASES[key]))
    return item


def city_bbox(
    country: str, city: str, *, scale: float = 1.0
) -> tuple[float, float, float, float] | None:
    """Прямоугольник (юг, запад, север, восток) вокруг центра города.

    Радиус зависит от населения: ~2 км для небольшого города, до ~11 км для
    миллионника. scale > 1 — расширенный поиск по агломерации."""
    item = find(country, city)
    if not item:
        return None
    radius_km = min(12.0, max(2.0, 1.5 + math.sqrt(max(item["population"], 0)) / 400)) * scale
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.2, math.cos(math.radians(item["lat"]))))
    return (
        round(item["lat"] - dlat, 5), round(item["lon"] - dlon, 5),
        round(item["lat"] + dlat, 5), round(item["lon"] + dlon, 5),
    )


def search_order(country: str, rng: random.Random | None = None) -> list[str]:
    """Крупные города страны, начиная со случайного: повторные поиски охватывают разные города."""
    items = cities(country)[:AUTO_CITIES]
    if not items:
        return []
    start = (rng or random).randrange(len(items))
    return items[start:] + items[:start]


def public_list() -> list[dict]:
    return [
        {"code": code, "title": COUNTRIES[code]["title"], "cities": COUNTRIES[code]["cities"]}
        for code in ORDER
    ]
