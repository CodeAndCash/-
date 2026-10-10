import asyncio
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai
from . import db

AI_TOTAL_TIMEOUT = 45  # секунд на всю генерацию нейросетью
FREE_TEMPLATE_REFUNDS = 3  # сколько шаблонов в день не списываем, если нейросеть упала
from . import generator
from . import library_data
from .auth import verify_init_data
from .config import (
    ADMIN_IDS,
    AI_DAILY_LIMIT,
    AI_ENABLED,
    AI_USER_DAILY_LIMIT,
    CONTACT_USERNAME,
    JOIN_URL,
    ROOT_DIR,
    TRIAL_GENERATIONS,
    is_admin_user,
)

log = logging.getLogger("script_cc.api")
WORKERS: set[asyncio.Task] = set()
AI_SEMAPHORE = asyncio.Semaphore(4)
IN_FLIGHT: set[int] = set()
MAX_SAVED = 300
LOCK_PREVIEW = 110

TRIAL_OVER_TEXT = (
    "Пробный доступ закончился.\n"
    "Вы использовали {used} {word}.\n"
    "Чтобы продолжить создавать скрипты и пользоваться библиотекой Script C&C, вступите в команду C&C Family,\n"
    "подробности можно узнать у @{contact}."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init()
    await db.seed_library(library_data.ITEMS)
    yield
    for task in list(WORKERS):
        task.cancel()
    if WORKERS:
        await asyncio.gather(*WORKERS, return_exceptions=True)


app = FastAPI(title="Script C&C API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def gen_word(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "генерацию"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "генерации"
    return "генераций"


def trial_over_message() -> str:
    total = TRIAL_GENERATIONS
    return TRIAL_OVER_TEXT.format(used=total, word=gen_word(total), contact=CONTACT_USERNAME)


async def current_user(init_data: str | None) -> dict:
    user = verify_init_data(init_data or "")
    if not user:
        raise HTTPException(401, "Не удалось проверить вход Telegram. Закройте и откройте приложение снова.")
    row = await db.upsert_user(user["id"], user.get("username"), user.get("first_name"))
    if row.get("banned") and row["id"] not in ADMIN_IDS:
        raise HTTPException(
            403,
            {
                "code": "banned",
                "message": f"Вы забанены, свяжитесь с @{CONTACT_USERNAME}\nЧтобы узнать причину.",
                "contact": CONTACT_USERNAME,
            },
        )
    return row


def is_admin(user: dict) -> bool:
    return bool(user["is_admin"]) or is_admin_user(user["id"], user.get("username"))


def require_admin(user: dict) -> None:
    if not is_admin(user):
        raise HTTPException(403, "Только для администратора.")


async def access_info(user: dict) -> dict:
    member = db.is_member(user)
    info = {
        "plan": "member" if member else "trial",
        "trial_total": TRIAL_GENERATIONS,
        "join": JOIN_URL,
        "contact": CONTACT_USERNAME,
    }
    if member:
        info.update(limit=user["daily_limit"], used=await db.used_today(user["id"]), bonus=int(user.get("bonus") or 0))
    else:
        left = db.trial_left(user)
        info.update(left=left, trial_over=left <= 0)
        if left <= 0:
            info["trial_message"] = trial_over_message()
    return info


def meta_payload() -> dict:
    return {
        "purposes": [{"id": key, "title": value[0]} for key, value in generator.PURPOSES.items()],
        "channels": [{"id": key, "title": value} for key, value in generator.CHANNELS.items()],
        "tones": [{"id": key, "title": value[0]} for key, value in generator.TONES.items()],
        "niche_hints": generator.NICHE_HINTS,
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/me")
async def api_me(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    await db.mark_app_opened(user["id"])
    return {
        "id": user["id"],
        "name": user["first_name"],
        "username": user["username"],
        "is_admin": is_admin(user),
        "access": await access_info(user),
        "stats": await db.user_stats(user["id"]),
        "ai": AI_ENABLED,
        **meta_payload(),
    }


# ---------- Библиотека ----------

@app.get("/api/library")
async def api_library(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    member = db.is_member(user)
    items = []
    for row in await db.list_library():
        locked = not member and not row["free"]
        body = row["body"]
        if locked:
            body = body[:LOCK_PREVIEW].rstrip() + "…"
        items.append(
            {
                "id": row["id"],
                "category": row["category"],
                "title": row["title"],
                "body": body,
                "free": bool(row["free"]),
                "locked": locked,
            }
        )
    return {"items": items}


# ---------- Генерация ----------

class GenerateRequest(BaseModel):
    niche: str = Field(default="", max_length=80)
    purpose: str = Field(default="first", pattern=r"^[a-z]{3,12}$")
    channel: str = Field(default="telegram", pattern=r"^[a-z]{3,12}$")
    tone: str = Field(default="friendly", pattern=r"^[a-z]{3,12}$")
    details: str = Field(default="", max_length=700)
    variant: int = Field(default=0, ge=0, le=1000)


async def _ai_text(user_id: int, prompt: str) -> tuple[str, str]:
    """Возвращает (текст, причина отказа). Пустой текст — использовать шаблон."""
    if not AI_ENABLED:
        return "", "no_ai"
    if not await db.reserve_api_call(f"ai:{user_id}", AI_USER_DAILY_LIMIT, period="day"):
        return "", "user_limit"
    if not await db.reserve_api_call("ai", AI_DAILY_LIMIT, period="day"):
        await db.refund_api_call(f"ai:{user_id}")
        return "", "global_limit"
    try:
        # Ограничиваем всё ожидание: прокси Vercel не ждёт бесконечно, а человек — тем более.
        return await asyncio.wait_for(_ai_call(prompt), timeout=AI_TOTAL_TIMEOUT), ""
    except Exception as exc:  # AIError, таймаут или любая неожиданная ошибка — отдаём шаблон
        if not isinstance(exc, ai.AIError):
            log.exception("AI call failed")
        message = str(exc) if isinstance(exc, ai.AIError) else (
            "Нейросеть не ответила вовремя." if isinstance(exc, asyncio.TimeoutError) else f"Ошибка нейросети: {type(exc).__name__}"
        )
        await db.log_source_error("ai", message)
        await db.refund_api_call(f"ai:{user_id}")
        await db.refund_api_call("ai")
        return "", "ai_error"


async def _ai_call(prompt: str) -> str:
    async with AI_SEMAPHORE:
        return await ai.complete(prompt)


@app.post("/api/generate")
async def api_generate(body: GenerateRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    uid = user["id"]
    if body.purpose not in generator.PURPOSES:
        raise HTTPException(422, "Выберите, для чего нужен скрипт.")
    channel = body.channel if body.channel in generator.CHANNELS else "telegram"
    tone = body.tone if body.tone in generator.TONES else "friendly"
    niche = generator._clean(body.niche, 80)
    details = generator._clean(body.details, 700)
    if len(niche) < 2 and len(details) < 8:
        raise HTTPException(422, "Напишите нишу или коротко опишите, какой скрипт нужен.")
    if uid in IN_FLIGHT:
        raise HTTPException(429, "Предыдущий скрипт ещё пишется. Подождите пару секунд.")
    IN_FLIGHT.add(uid)
    try:
        status, kind, day = await db.reserve_generation(uid)
        if status == "trial_over":
            raise HTTPException(403, {"code": "trial_over", "message": trial_over_message(), "join": JOIN_URL, "contact": CONTACT_USERNAME})
        if status == "limit":
            raise HTTPException(429, {"code": "limit", "message": f"Дневной лимит исчерпан ({user['daily_limit']}). Он обновится завтра, или напишите @{CONTACT_USERNAME}, чтобы увеличить."})
        if status != "ok":
            raise HTTPException(403, "Доступ закрыт.")
        try:
            prompt = generator.build_prompt(niche, body.purpose, channel, tone, details, body.variant)
            text, note = await _ai_text(uid, prompt)
            if text:
                text = generator.clean_output(text)
            refunded = False
            if not text:
                text = generator.template_script(niche, body.purpose, body.variant)
                # Нейросеть упала не по вине человека — несколько раз в день такую генерацию
                # не списываем. Иначе (нейросеть не подключена или сбой затянулся) списываем,
                # чтобы пробный доступ и дневной лимит не становились бесконечными.
                if note in ("ai_error", "global_limit") and await db.reserve_api_call(
                    f"tpl:{uid}", FREE_TEMPLATE_REFUNDS, period="day"
                ):
                    await db.refund_generation(uid, kind, day)
                    kind = ""
                    refunded = True
        except Exception:
            await db.refund_generation(uid, kind, day)
            raise
        await db.log_generation(uid, niche, body.purpose, channel, "ai" if not note else "template")
    finally:
        IN_FLIGHT.discard(uid)
    fresh = await db.get_user(uid) or user
    return {
        "text": text,
        "source": "ai" if not note else "template",
        "note": note,
        "refunded": refunded,
        "title": generator.make_title(body.purpose, niche),
        "access": await access_info(fresh),
    }


# ---------- Мои скрипты ----------

class SavedBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=4000)
    niche: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=12)


@app.get("/api/saved")
async def api_saved(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    return {"items": await db.list_saved(user["id"])}


@app.post("/api/saved")
async def api_saved_create(body: SavedBody, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    if await db.count_saved(user["id"]) >= MAX_SAVED:
        raise HTTPException(400, f"Можно хранить до {MAX_SAVED} скриптов. Удалите ненужные.")
    purpose = body.purpose if body.purpose in generator.PURPOSES else ""
    saved_id = await db.save_saved(user["id"], body.title.strip(), body.body.strip(), body.niche.strip(), purpose)
    return {"ok": True, "id": saved_id}


@app.put("/api/saved/{saved_id}")
async def api_saved_update(
    saved_id: int, body: SavedBody, x_init_data: str | None = Header(None, alias="X-Init-Data")
):
    user = await current_user(x_init_data)
    if not await db.save_saved(user["id"], body.title.strip(), body.body.strip(), saved_id=saved_id):
        raise HTTPException(404, "Скрипт не найден.")
    return {"ok": True}


@app.delete("/api/saved/{saved_id}")
async def api_saved_delete(saved_id: int, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    if not await db.delete_saved(user["id"], saved_id):
        raise HTTPException(404, "Скрипт не найден.")
    return {"ok": True}


# ---------- Ключ доступа ----------

class KeyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)


KEY_RESULTS = {
    "not_found": "Ключ не найден. Проверьте, что он введён без ошибок.",
    "used": "Этот ключ уже использован.",
    "other_user": "Этот ключ выдан другому пользователю.",
    "already": "Вы уже активировали этот ключ.",
    "banned": "Доступ закрыт администратором.",
}


@app.post("/api/key")
async def api_key(body: KeyRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    result, key = await db.redeem_key(user["id"], user["username"], body.code.strip())
    if result != "ok":
        raise HTTPException(400, KEY_RESULTS[result])
    parts = []
    if key["daily_limit"] > 0:
        parts.append(f"полный доступ, {key['daily_limit']} генераций в день")
    if key["bonus"] > 0:
        parts.append(f"+{key['bonus']} бонусных генераций")
    await _notify_access(user["id"], limit=key["daily_limit"] or None, bonus=key["bonus"], by_key=True)
    return {"ok": True, "message": "Ключ активирован: " + ", ".join(parts) + "."}


async def _notify(user_id: int, message: str) -> None:
    try:
        from .bot import bot

        await bot.send_message(user_id, message)
    except Exception:
        log.exception("Could not notify user %s", user_id)


async def _notify_access(user_id: int, **kwargs) -> None:
    try:
        from .bot import send_access_opened

        await send_access_opened(user_id, **kwargs)
    except Exception:
        log.exception("Could not send access message to %s", user_id)


async def _notify_closed(user_id: int) -> None:
    try:
        from .bot import send_access_closed

        await send_access_closed(user_id)
    except Exception:
        log.exception("Could not send closed message to %s", user_id)


# ---------- Админ-панель ----------

def _user_json(row: dict) -> dict:
    member = bool(row["approved"]) or bool(row["is_admin"])
    return {
        "id": row["id"],
        "n": "@" + row["username"] if row.get("username") else (row.get("first_name") or f"id{row['id']}"),
        "g": row.get("gens", 0),
        "s": row.get("saved", 0),
        "t": row.get("today", 0),
        "lim": row["daily_limit"],
        "approved": bool(row["approved"]),
        "is_admin": bool(row["is_admin"]),
        "banned": bool(row.get("banned")),
        "plan": "member" if member else "trial",
        "trial_used": row.get("trial_used", 0),
        "bonus": row.get("bonus", 0),
        "trial_left": None if member else db.trial_left(row),
    }


@app.get("/api/admin/users")
async def admin_users(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"users": [_user_json(row) for row in await db.all_users_stats()]}


class LimitRequest(BaseModel):
    limit: int = Field(ge=0, le=5000)


@app.post("/api/admin/users/{user_id}/limit")
async def admin_limit(user_id: int, body: LimitRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.set_limit(user_id, body.limit):
        raise HTTPException(404, "Пользователь не найден.")
    await _notify(user_id, f"<b>Лимит изменён</b>\n\nТеперь вам доступно <b>{body.limit}</b> генераций в день.")
    return {"ok": True}


class AccessRequest(BaseModel):
    approved: bool


@app.post("/api/admin/users/{user_id}/access")
async def admin_access(user_id: int, body: AccessRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if user_id == user["id"]:
        raise HTTPException(400, "Нельзя закрыть собственный доступ владельца.")
    if user_id <= 0:
        raise HTTPException(400, "Telegram ID должен быть положительным числом.")
    if body.approved:
        await db.grant_member(user_id)
        await _notify_access(user_id)
    else:
        if not await db.set_approved(user_id, 0):
            raise HTTPException(404, "Пользователь не найден.")
        await _notify_closed(user_id)
    return {"ok": True}


class BanRequest(BaseModel):
    banned: bool


@app.post("/api/admin/users/{user_id}/ban")
async def admin_ban(user_id: int, body: BanRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if user_id == user["id"] or user_id in ADMIN_IDS:
        raise HTTPException(400, "Нельзя заблокировать владельца.")
    if not await db.set_banned(user_id, body.banned):
        raise HTTPException(404, "Пользователь не найден.")
    return {"ok": True}


class BonusRequest(BaseModel):
    amount: int = Field(ge=-1000, le=1000)


@app.post("/api/admin/users/{user_id}/bonus")
async def admin_bonus(user_id: int, body: BonusRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    bonus = await db.add_bonus(user_id, body.amount)
    if bonus is None:
        raise HTTPException(404, "Пользователь не найден. Он должен хотя бы раз открыть бота.")
    if body.amount > 0:
        await _notify(user_id, f"<b>Добавлены генерации</b>\n\nВам добавлено бонусных генераций: <b>{body.amount}</b>.\nОткройте Script C&amp;C.")
    return {"ok": True, "bonus": bonus}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    """Удалить участника: он сразу заблокирован в боте и пропадает из списков."""
    user = await current_user(x_init_data)
    require_admin(user)
    if user_id == user["id"] or user_id in ADMIN_IDS:
        raise HTTPException(400, "Нельзя удалить владельца.")
    if not await db.delete_user(user_id):
        raise HTTPException(404, "Пользователь не найден.")
    return {"ok": True}


class GrantRequest(BaseModel):
    query: str = Field(min_length=1, max_length=64)
    limit: int | None = Field(default=None, ge=1, le=5000)


@app.post("/api/admin/grant")
async def admin_grant(body: GrantRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    """Выдать полный доступ по @username или Telegram ID."""
    user = await current_user(x_init_data)
    require_admin(user)
    query = body.query.strip()
    target = await db.find_user(query)
    if not target:
        if query.isdigit() and int(query) > 0:
            await db.grant_member(int(query), body.limit)
            return {"ok": True, "message": f"Доступ выдан ID {query}. Пусть откроет бота."}
        raise HTTPException(
            404,
            "Пользователь с таким @username ещё не открывал бота. Попросите его нажать /start "
            "или выдайте доступ по Telegram ID либо ключом.",
        )
    await db.grant_member(target["id"], body.limit)
    await _notify_access(target["id"])
    name = "@" + target["username"] if target.get("username") else f"ID {target['id']}"
    return {"ok": True, "message": f"Доступ выдан {name}."}


class KeyCreate(BaseModel):
    for_user: str = Field(default="", max_length=64)
    limit: int | None = Field(default=None, ge=0, le=5000)
    bonus: int = Field(default=0, ge=0, le=1000)
    uses: int = Field(default=1, ge=1, le=1000)
    note: str = Field(default="", max_length=120)


@app.get("/api/admin/keys")
async def admin_keys(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"keys": await db.list_keys()}


@app.post("/api/admin/keys")
async def admin_key_create(body: KeyCreate, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if body.limit == 0 and body.bonus == 0:
        raise HTTPException(422, "Ключ должен давать доступ или бонусные генерации.")
    for_user = body.for_user.strip()
    if for_user and not re.fullmatch(r"@?[A-Za-z0-9_]{3,32}|\d{3,15}", for_user):
        raise HTTPException(422, "Укажите @username или числовой Telegram ID.")
    for _ in range(5):
        code = "CC-" + "-".join(secrets.token_hex(2).upper() for _ in range(3))
        if await db.create_key(code, for_user, body.limit, body.bonus, body.uses, body.note.strip()):
            return {"ok": True, "code": code}
    raise HTTPException(500, "Не удалось создать ключ, попробуйте ещё раз.")


class DefaultLimitRequest(BaseModel):
    limit: int = Field(ge=1, le=5000)
    scope: str = Field(default="standard", pattern=r"^(new|standard|all)$")


@app.get("/api/admin/settings")
async def admin_settings(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"default_limit": db.default_limit()}


@app.post("/api/admin/settings/limit")
async def admin_default_limit(body: DefaultLimitRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    changed = await db.set_default_limit(body.limit, body.scope)
    tail = {
        "new": "Он будет у новых участников и новых ключей.",
        "standard": f"Поменяли тем, у кого стоял прежний стандартный лимит: {changed}.",
        "all": f"Поменяли всем участникам: {changed}.",
    }[body.scope]
    return {"ok": True, "default_limit": body.limit, "changed": changed,
            "message": f"Лимит по умолчанию: {body.limit} генераций в день. {tail}"}


@app.delete("/api/admin/keys/{code}")
async def admin_key_delete(code: str, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.delete_key(code):
        raise HTTPException(404, "Ключ не найден.")
    return {"ok": True}


@app.get("/api/admin/members")
async def admin_members(
    q: str = Query("", max_length=64), x_init_data: str | None = Header(None, alias="X-Init-Data")
):
    """Все, кто запускал бота: юзернейм, ID и открывал ли мини‑апп."""
    user = await current_user(x_init_data)
    require_admin(user)
    items = await db.members(q)
    return {"members": items, "total": len(items), "opened": sum(1 for item in items if item["app_opened"])}


@app.get("/api/admin/overview")
async def admin_overview(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    data = await db.admin_overview()
    data["errors"] = await db.source_errors()
    data["api"] = {"ai_day": await db.api_calls("ai", "day"), "ai_limit": AI_DAILY_LIMIT, "ai_enabled": AI_ENABLED}
    data["purpose_titles"] = {key: value[0] for key, value in generator.PURPOSES.items()}
    return data


@app.get("/api/admin/requests")
async def admin_requests(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    rows = await db.recent_requests()
    for row in rows:
        row["who"] = "@" + row["username"] if row.get("username") else (row.get("first_name") or f"id{row['user_id']}")
        row["purpose_title"] = generator.PURPOSES.get(row["purpose"], ("", ""))[0] or row["purpose"]
    return {"items": rows}


class LibraryBody(BaseModel):
    category: str = Field(pattern=r"^[a-z]{3,12}$")
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=4000)
    free: bool = False


@app.get("/api/admin/library")
async def admin_library(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    items = [
        {"id": r["id"], "category": r["category"], "title": r["title"], "body": r["body"], "free": bool(r["free"])}
        for r in await db.list_library()
    ]
    return {"items": items}


@app.post("/api/admin/library")
async def admin_library_create(body: LibraryBody, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if body.category not in generator.PURPOSES:
        raise HTTPException(422, "Неизвестная категория.")
    item_id = await db.save_library_item(body.category, body.title.strip(), body.body.strip(), body.free)
    return {"ok": True, "id": item_id}


@app.put("/api/admin/library/{item_id}")
async def admin_library_update(
    item_id: int, body: LibraryBody, x_init_data: str | None = Header(None, alias="X-Init-Data")
):
    user = await current_user(x_init_data)
    require_admin(user)
    if body.category not in generator.PURPOSES:
        raise HTTPException(422, "Неизвестная категория.")
    if not await db.get_library_item(item_id):
        raise HTTPException(404, "Скрипт не найден.")
    await db.save_library_item(body.category, body.title.strip(), body.body.strip(), body.free, item_id)
    return {"ok": True}


@app.delete("/api/admin/library/{item_id}")
async def admin_library_delete(item_id: int, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.delete_library_item(item_id):
        raise HTTPException(404, "Скрипт не найден.")
    return {"ok": True}


class BroadcastRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    image: str = Field(default="", max_length=7_000_000)  # data:image/...;base64,...


_TAG_RE = re.compile(
    r"&lt;(?:(?P<close>/)(?P<ctag>b|i|u|s|code|a)|(?P<otag>b|i|u|s|code)|a href=&quot;(?P<href>https?://[^\s\"<>]+?)&quot;)&gt;"
)


def telegram_html(text: str) -> str:
    """Экранирует всё, кроме разрешённых тегов Telegram: <b> <i> <u> <s> <code> <a href>.
    Закрывающий тег превращается в настоящий, только если он закрывает последний открытый;
    в конце всё незакрытое закрывается в обратном порядке — Telegram такой текст всегда примет."""
    import html as _html

    escaped = _html.escape(text, quote=True)
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(escaped):
        out.append(escaped[pos:match.start()])
        pos = match.end()
        if match.group("close"):
            tag = match.group("ctag")
            if stack and stack[-1] == tag:
                stack.pop()
                out.append(f"</{tag}>")
            else:
                out.append(match.group(0))  # лишний закрывающий тег — оставляем текстом
        elif match.group("otag"):
            if "code" in stack:
                out.append(match.group(0))
            else:
                stack.append(match.group("otag"))
                out.append(f"<{match.group('otag')}>")
        else:
            if "a" in stack or "code" in stack:
                out.append(match.group(0))
            else:
                stack.append("a")
                out.append(f'<a href="{match.group("href")}">')
    out.append(escaped[pos:])
    out.extend(f"</{tag}>" for tag in reversed(stack))
    return "".join(out).strip()


def _decode_image(data_url: str) -> bytes | None:
    import base64

    if not data_url:
        return None
    match = re.fullmatch(r"data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\s]+)", data_url.strip())
    if not match:
        raise HTTPException(422, "Картинка должна быть JPG, PNG или WEBP.")
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", match.group(2)) + "==", validate=False)
    except (ValueError, TypeError):
        raise HTTPException(422, "Картинка повреждена, выберите другую.")
    if not raw:
        raise HTTPException(422, "Картинка повреждена, выберите другую.")
    if len(raw) > 5_000_000:
        raise HTTPException(422, "Картинка больше 5 МБ.")
    return raw



async def _run_broadcast(admin_id: int, message: str, image: bytes | None) -> None:
    try:
        from .bot import broadcast_to_all

        sent, total = await broadcast_to_all(message, image=image)
        await _notify(admin_id, f"<b>Рассылка завершена</b>\n\nДоставлено: <b>{sent}</b> из {total}.")
    except Exception:
        log.exception("Broadcast failed")
        await _notify(admin_id, "Рассылку не удалось завершить.")


@app.post("/api/admin/broadcast")
async def admin_broadcast(body: BroadcastRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    message = telegram_html(body.text.strip())
    image = _decode_image(body.image)
    if not message and not image:
        raise HTTPException(422, "Добавьте текст или картинку.")
    import html as _html

    if len(_html.unescape(re.sub(r"<[^>]+>", "", message))) > 4000:
        raise HTTPException(422, "Текст длиннее 4000 символов.")
    task = asyncio.create_task(_run_broadcast(user["id"], message, image))
    WORKERS.add(task)
    task.add_done_callback(WORKERS.discard)
    return {"ok": True, "message": "Рассылка запущена. Результат придёт в чат с ботом."}


static_dir = Path(ROOT_DIR) / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="miniapp")
