"""Материалы для мини-аппа: списки, закрытые страницы, прогресс, марафон."""
from __future__ import annotations

import datetime as dt
import json
import re

from . import config, db

MSK = dt.timezone(dt.timedelta(hours=3))

KINDS = {
    "lesson": "урок",
    "material": "материал",
    "prompt": "промпт",
    "resource": "подборка",
    "agent": "помощник",
    "skill": "скилл",
    "plugin": "плагин",
    "cskill": "скилл для Codex",
    "cplugin": "плагин для Codex",
    "free": "шаг FreeBot-марафона",
    "guide": "памятка",
    "marathon": "день марафона",
    "post": "пост",
    "review": "отзыв",
}


def outline(body: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", body or "", re.M)][:12]


def intro(body: str) -> str:
    """Первый абзац — его видно и без доступа."""
    for block in re.split(r"\n\s*\n", body or ""):
        block = block.strip()
        if block and not block.startswith(("#", "-", "```", ">", "1.")):
            return block[:600]
    return ""


def can_open(item: dict, user: dict | None) -> bool:
    return bool(item.get("free")) or item.get("kind") in ("marathon", "review", "guide", "free") or db.is_resident(user)


def card(item: dict, user: dict | None, done: dict[int, int]) -> dict:
    """Короткая карточка без текста — для списков."""
    return {
        "id": item["id"], "kind": item["kind"], "module": item["module"], "title": item["title"],
        "subtitle": item["subtitle"], "icon": item["icon"], "free": bool(item["free"]),
        "locked": not can_open(item, user), "done": item["id"] in done, "minutes": item["minutes"],
        "position": item["position"], "media": media(item),
    }


def media(item: dict) -> list[str]:
    try:
        value = json.loads(item.get("media") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value if isinstance(v, str)][:6]


async def listing(kind: str, user: dict | None) -> list[dict]:
    done = await db.done_ids(user["id"]) if user else {}
    return [card(i, user, done) for i in await db.list_content(kind)]


def _neighbors(items: list[dict], cid: int) -> tuple[dict | None, dict | None]:
    ids = [i["id"] for i in items]
    if cid not in ids:
        return None, None
    k = ids.index(cid)
    return (items[k - 1] if k > 0 else None), (items[k + 1] if k + 1 < len(items) else None)


async def detail(cid: int, user: dict | None) -> dict | None:
    item = await db.get_content(cid)
    if not item or (not item["published"] and not (user and config.is_admin_user(user["id"], user.get("username")))):
        return None
    done = await db.done_ids(user["id"]) if user else {}
    out = card(item, user, done)
    siblings = await db.list_content(item["kind"])
    prev, nxt = _neighbors(siblings, cid)
    out["prev"] = {"id": prev["id"], "title": prev["title"]} if prev else None
    out["next"] = ({"id": nxt["id"], "title": nxt["title"], "subtitle": nxt["subtitle"],
                    "locked": not can_open(nxt, user)} if nxt else None)
    if item["kind"] == "marathon":
        state = await marathon_state(user["id"] if user else 0, user)
        day = next((d for d in state["days"] if d["id"] == cid), None)
        if day and not day["open"]:
            out.update(locked=True, body="", intro=intro(item["body"]), outline=outline(item["body"]),
                       closed_reason=day.get("reason", ""))
            return out
    if out["locked"]:
        out.update(body="", intro=intro(item["body"]), outline=outline(item["body"]))
    else:
        out["body"] = item["body"]
    return out


async def marathon_state(uid: int, user: dict | None = None) -> dict:
    """День открывается на следующий календарный день после того, как закрыт предыдущий."""
    items = await db.list_content("marathon")
    done = await db.done_ids(uid) if uid else {}
    user = user or (await db.get_user(uid) if uid else None)
    admin = bool(user) and config.is_admin_user(user["id"], user.get("username"))
    today = dt.datetime.now(MSK).date()
    days = []
    prev_done_at = None
    for index, item in enumerate(items):
        is_done = item["id"] in done
        if index == 0 or admin:
            open_, reason = True, ""
        elif prev_done_at is None:
            open_, reason = False, "Сначала закрой предыдущий день"
        elif dt.datetime.fromtimestamp(prev_done_at, MSK).date() >= today:
            open_, reason = False, "Откроется завтра"
        else:
            open_, reason = True, ""
        days.append({"id": item["id"], "day": index + 1, "title": item["title"], "subtitle": item["subtitle"],
                     "minutes": item["minutes"], "done": is_done, "open": open_ or is_done, "reason": reason})
        prev_done_at = done.get(item["id"])
    current = next((d for d in days if not d["done"]), None)
    return {"days": days, "done": sum(d["done"] for d in days), "total": len(days), "current": current}


async def counts() -> dict:
    items = await db.list_content()
    by: dict[str, int] = {}
    modules: set[str] = set()
    for item in items:
        by[item["kind"]] = by.get(item["kind"], 0) + 1
        if item["kind"] == "lesson" and item["module"]:
            modules.add(item["module"])
    by["modules"] = len(modules)
    by["free_lessons"] = sum(1 for i in items if i["kind"] == "lesson" and i["free"])
    return by
