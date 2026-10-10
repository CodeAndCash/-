"""Какие ниши сейчас больше всего нуждаются в сайте или Telegram-боте.

Оценку даёт нейросеть по списку наших ниш (раз в сутки на страну, ответ кешируется).
Если нейросеть не подключена или не ответила — показывается базовая оценка."""

from __future__ import annotations

import json
import re
import time

from . import niches

# Базовая оценка: где запись и быстрые ответы клиентам важнее всего.
BASE = {
    0: (9, "Запись к конкретному мастеру и напоминания — клиенты уходят к тем, у кого можно записаться онлайн.",
        "Сайт с записью к мастеру + Telegram-бот с напоминаниями"),
    6: (9, "Мастера ведут запись в переписке и теряют клиентов; нужен бот со свободными окнами.",
        "Telegram-бот записи на свободные окна + простой сайт с ценами"),
    1: (8, "Много услуг и мастеров — без онлайн-записи администратор не успевает отвечать.",
        "Сайт с услугами и ценами + онлайн-запись"),
    3: (8, "Пациенты выбирают клинику по сайту и врачам; напоминания снижают неявки.",
        "Сайт клиники с врачами и записью + бот-напоминания"),
    2: (7, "Клиенты сравнивают цены и ищут запись на ремонт; сезонные напоминания дают повторы.",
        "Сайт с услугами и ценами + бот записи и напоминаний о ТО"),
    4: (7, "Расписание, пробная тренировка и продление абонементов удобнее всего через бота.",
        "Бот с расписанием и записью + сайт с абонементами"),
    9: (7, "Владельцы питомцев ищут клинику срочно; напоминания о прививках возвращают клиентов.",
        "Сайт с услугами и записью + бот-напоминания о прививках"),
    10: (6, "Родители сравнивают школы онлайн; запись на пробный урок решает выбор.",
         "Сайт с программами и записью на пробный урок + бот"),
    8: (6, "Гости хотят забронировать стол онлайн; без брони часть уходит к соседям.",
        "Сайт с меню и онлайн-бронью + бот бронирования"),
    7: (5, "Меню и предзаказ онлайн, карта лояльности в Telegram удерживают гостей.",
        "Бот с меню, предзаказом и карточкой лояльности"),
}

_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_SECONDS = 24 * 3600


def base_items() -> list[dict]:
    items = [
        {"id": key, "niche": niches.NICHES[key]["title"], "score": score, "why": why, "offer": offer}
        for key, (score, why, offer) in BASE.items()
    ]
    items.sort(key=lambda item: -item["score"])
    return items


def prompt(country_title: str) -> str:
    titles = [niches.NICHES[key]["title"] for key in niches.ORDER]
    return (
        "Оцени, каким нишам малого бизнеса сейчас больше всего нужны сайт или Telegram-бот "
        f"(страна: {country_title}). Ниши: " + "; ".join(titles) + ".\n"
        "Верни ТОЛЬКО JSON-массив без пояснений, по одному объекту на нишу, от самой "
        'нуждающейся к наименее: [{"niche": "точное название из списка", "score": число 1-10, '
        '"why": "одно короткое предложение, почему", "offer": "что именно предложить, до 10 слов"}]. '
        "Пиши по-русски, без выдуманных цифр и процентов."
    )


def parse(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except ValueError:
        return []
    by_title = {niches.NICHES[key]["title"].lower(): key for key in niches.ORDER}
    items, seen = [], set()
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict):
            continue
        key = by_title.get(str(row.get("niche", "")).strip().lower())
        if key is None or key in seen:
            continue
        seen.add(key)
        try:
            score = max(1, min(10, int(row.get("score", 5))))
        except (TypeError, ValueError):
            score = 5
        items.append({
            "id": key, "niche": niches.NICHES[key]["title"], "score": score,
            "why": str(row.get("why", ""))[:220], "offer": str(row.get("offer", ""))[:120],
        })
    items.sort(key=lambda item: -item["score"])
    return items if len(items) >= 5 else []


def cached(country: str) -> list[dict] | None:
    hit = _cache.get(country)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    return None


def remember(country: str, items: list[dict]) -> None:
    _cache[country] = (time.time(), items)
