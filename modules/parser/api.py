import asyncio
import logging
import re
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import contacts as cn
from . import countries
from . import db
from . import demand
from . import niches
from . import scripts
from .auth import verify_init_data
from .config import (
    ADMIN_IDS,
    AI_DAILY_LIMIT,
    AI_USER_DAILY_LIMIT,
    CONTACT_USERNAME,
    AI_ENABLED,
    GEOAPIFY_DAILY_CREDITS,
    DGIS_MONTHLY_LIMIT,
    GOOGLE_MONTHLY_LIMIT,
    JOIN_URL,
    ROOT_DIR,
    TRIAL_LEADS,
    TRIAL_SEARCHES,
    is_admin_user,
)
from .lead_identity import claim_tokens
from . import parser as search_engine
from .parser import GeoError, normalize_url, run_search

log = logging.getLogger("parser_cc.api")
STATUSES = {"new", "written", "replied", "rejected", "client"}
WORKERS: set[asyncio.Task] = set()
SEARCH_SEMAPHORE = asyncio.Semaphore(3)
DEMAND_MIN_SAMPLE = 30

TRIAL_OVER_TEXT = (
    "Пробный доступ закончился.\n"
    "Вы использовали пробный запрос и нашли {found} {word}.\n"
    "Чтобы продолжить получать лиды и пользоваться Parser C&C, вступите в команду C&C Family,\n"
    "подробности можно узнать у @{contact}."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init()
    await db.seed_scripts(scripts.defaults())
    search_engine.CACHE_GET = db.osm_cache_get
    search_engine.CACHE_SET = db.osm_cache_set
    yield
    for task in list(WORKERS):
        task.cancel()
    if WORKERS:
        await asyncio.gather(*WORKERS, return_exceptions=True)


app = FastAPI(
    title="Parser C&C API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def lead_word(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "лид"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "лида"
    return "лидов"


def trial_over_payload(found: int | None = None) -> dict:
    return {
        "code": "trial_over",
        "message": TRIAL_OVER_TEXT.format(
            found=TRIAL_LEADS if found is None else found,
            word=lead_word(TRIAL_LEADS if found is None else found),
            contact=CONTACT_USERNAME,
        ),
        "join": JOIN_URL,
        "contact": CONTACT_USERNAME,
    }


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
        "trial_searches": TRIAL_SEARCHES,
        "trial_leads": TRIAL_LEADS,
        "join": JOIN_URL,
        "contact": CONTACT_USERNAME,
    }
    if member:
        info.update(limit=user["daily_limit"], used=await db.used_today(user["id"]), max_count=200)
    else:
        left = db.trial_left(user, TRIAL_SEARCHES)
        info.update(searches_left=left, max_count=TRIAL_LEADS, trial_over=left <= 0)
        if left <= 0:
            found = (await db.stats(user["id"])).get("found", 0)
            info["trial_message"] = trial_over_payload(found)["message"]
    return info


@app.get("/api/me")
async def api_me(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    await db.mark_app_opened(user["id"])
    access = await access_info(user)
    return {
        "id": user["id"],
        "name": user["first_name"],
        "username": user["username"],
        "is_admin": is_admin(user),
        "limit": user["daily_limit"],
        "used": await db.used_today(user["id"]),
        "access": access,
        "niches": niches.public_list(),
        "countries": countries.public_list(),
        "ai": AI_ENABLED,
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


class SearchRequest(BaseModel):
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    city: str = Field(default="", max_length=80)
    niche: int = Field(ge=0, le=99)
    custom: str = Field(default="", max_length=80)
    flt: str = Field(default="both", pattern=r"^(none|weak|both|bot|all)$")
    count: int = Field(ge=1, le=200)


@app.post("/api/search")
async def api_search(
    request: SearchRequest,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    if not niches.valid(request.niche):
        raise HTTPException(422, "Неизвестная ниша.")
    if request.niche == niches.CUSTOM and not search_engine.custom_term(request.custom):
        raise HTTPException(422, "Для своей ниши укажите слово для поиска: буквы или цифры.")

    trial = not db.is_member(user)
    count = request.count
    usage_day = db.today()
    if trial:
        count = min(count, TRIAL_LEADS)
        if not await db.reserve_trial(user["id"], TRIAL_SEARCHES):
            raise HTTPException(403, trial_over_payload())
        reserved = 0
    else:
        reserved_ok, usage_day = await db.reserve_usage(user["id"], count, user["daily_limit"])
        if not reserved_ok:
            remaining = max(0, user["daily_limit"] - await db.used_today(user["id"]))
            raise HTTPException(429, f"Дневной лимит исчерпан. Осталось: {remaining}.")
        reserved = count

    async def undo():
        if trial:
            await db.refund_trial(user["id"])
        else:
            await db.adjust_usage(user["id"], usage_day, -count)

    job_id = uuid.uuid4().hex
    try:
        await db.job_create(job_id, user["id"], count, reserved, usage_day, trial=trial)
    except sqlite3.IntegrityError as exc:
        await undo()
        raise HTTPException(409, "У вас уже выполняется поиск. Дождитесь его завершения.") from exc
    except Exception:
        await undo()
        raise

    params = request.model_copy(update={"count": count})
    task = asyncio.create_task(_worker(job_id, user["id"], params, usage_day, trial))
    WORKERS.add(task)
    task.add_done_callback(WORKERS.discard)
    return {"job_id": job_id, "count": count}


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


async def _notify_trial_over(user_id: int, found: int) -> None:
    try:
        from .bot import send_trial_over

        await send_trial_over(user_id, found)
    except Exception:
        log.exception("Could not send trial message to %s", user_id)


async def _worker(
    job_id: str, user_id: int, request: SearchRequest, usage_day: str, trial: bool = False
) -> None:
    progress_state = {"found": 0, "checked": 0}

    async def refund():
        if trial:
            await db.refund_trial(user_id)
        else:
            await db.adjust_usage(user_id, usage_day, -request.count)

    try:
        exclude_keys = await db.existing_lead_keys(user_id)
        exclude_leads = await db.existing_leads_for_dedupe(user_id)

        async def progress(found: int, checked: int) -> None:
            if checked - progress_state["checked"] >= 3 or found != progress_state["found"]:
                progress_state.update(found=found, checked=checked)
                await db.job_update(job_id, found=found, checked=checked)

        async def google_budget() -> bool:
            return await db.reserve_api_call("google", GOOGLE_MONTHLY_LIMIT)

        async def dgis_budget() -> bool:
            return await db.reserve_api_call("dgis", DGIS_MONTHLY_LIMIT)

        async def geo_budget(credits: int) -> bool:
            return await db.reserve_api_call(
                "geoapify", GEOAPIFY_DAILY_CREDITS, period="day", amount=credits
            )

        async with SEARCH_SEMAPHORE:
            leads = await run_search(
                request.country.upper(),
                request.city.strip(),
                request.niche,
                request.custom.strip(),
                request.flt,
                request.count,
                progress,
                exclude_keys,
                exclude_leads,
                google_budget,
                dgis_budget=dgis_budget,
                exclude_tokens=db.taken_tokens,
                geo_budget=geo_budget,
                on_source_error=db.log_source_error,
                on_analyzed=db.record_analyzed,
            )
        claimed = await db.claim_leads(user_id, leads)
        found = len(claimed)
        if trial:
            if found == 0:
                await db.refund_trial(user_id)
        else:
            charged = max(1, found)
            await db.adjust_usage(user_id, usage_day, charged - request.count)
        await db.job_update(
            job_id,
            status="done",
            found=found,
            checked=max(progress_state["checked"], found),
        )
        text = f"<b>Поиск завершён</b>\n\nНайдено новых лидов: <b>{found}</b>."
        if found:
            text += "\nОни уже во вкладке «Лиды»."
        if found < request.count:
            text += (
                "\n\nБольше новых организаций здесь не нашлось — "
                "попробуйте другой город или нишу."
            )
            if trial and found == 0:
                text += "\nПробный запрос не списан."
            elif not trial:
                text += "\nНеиспользованный лимит вернулся."
        await _notify(user_id, text)
        if trial and found:
            user = await db.get_user(user_id)
            if user and not db.is_member(user) and db.trial_left(user, TRIAL_SEARCHES) <= 0:
                await _notify_trial_over(user_id, found)
    except asyncio.CancelledError:
        await refund()
        await db.job_update(job_id, status="error", error="Поиск остановлен при остановке сервера.")
        raise
    except GeoError as exc:
        await refund()
        await db.job_update(job_id, status="error", error=str(exc))
    except Exception:
        log.exception("Search job %s failed", job_id)
        await refund()
        await db.job_update(job_id, status="error", error="Ошибка поиска. Попробуйте ещё раз позже.")


@app.get("/api/jobs/{job_id}")
async def api_job(
    job_id: str,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    job = await db.job_get(job_id, user["id"])
    if not job:
        raise HTTPException(404, "Поиск не найден.")
    result = {
        "status": job["status"],
        "total": job["total"],
        "found": job["found"],
        "checked": job["checked"],
        "error": job["error"],
    }
    if job["status"] == "done" and job.get("trial"):
        fresh = await db.get_user(user["id"])
        if fresh and not db.is_member(fresh) and db.trial_left(fresh, TRIAL_SEARCHES) <= 0:
            result["trial_over"] = trial_over_payload(job["found"])
    return result


@app.get("/api/leads")
async def api_leads(
    status: str = "all",
    limit: int = Query(1000, ge=1, le=5000),
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    if status != "all" and status not in STATUSES:
        raise HTTPException(400, "Неизвестный статус.")
    return {"leads": await db.list_leads(user["id"], status, limit)}


class StatusRequest(BaseModel):
    status: str


@app.post("/api/leads/{lead_id}/status")
async def api_status(
    lead_id: int,
    body: StatusRequest,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    if body.status not in STATUSES:
        raise HTTPException(400, "Неизвестный статус.")
    if not await db.set_status(user["id"], lead_id, body.status):
        raise HTTPException(404, "Лид не найден.")
    return {"ok": True}


@app.delete("/api/leads/{lead_id}")
async def api_lead_delete(lead_id: int, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    if not await db.delete_lead(user["id"], lead_id):
        raise HTTPException(404, "Лид не найден.")
    return {"ok": True}


@app.get("/api/stats")
async def api_stats(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    return await db.stats(user["id"])


@app.get("/api/demand")
async def api_demand(
    country: str = Query("", max_length=2),
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    """Какие ниши сейчас больше нуждаются в сайте или боте — оценка нейросети по нашим нишам."""
    await current_user(x_init_data)
    code = country.upper() if re.fullmatch(r"[A-Za-z]{2}", country or "") else "RU"
    items = demand.cached(code)
    if items is not None:
        return {"items": items, "source": "ai"}
    title = countries.COUNTRIES.get(code, {}).get("title", code)
    if AI_ENABLED and await db.reserve_api_call("ai", AI_DAILY_LIMIT, period="day"):
        try:
            items = demand.parse(await scripts.complete(demand.prompt(title), max_tokens=2500))
        except scripts.AIError as exc:
            await db.log_source_error("ai", str(exc))
            items = None
        if items:
            demand.remember(code, items)
            return {"items": items, "source": "ai"}
    return {"items": demand.base_items(), "source": "base"}


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
        parts.append(f"полный доступ, {key['daily_limit']} лидов в день")
    if key["bonus"] > 0:
        parts.append(f"+{key['bonus']} поисковых запросов")
    await _notify_access(user["id"], limit=key["daily_limit"] or None, bonus=key["bonus"], by_key=True)
    return {"ok": True, "message": "Ключ активирован: " + ", ".join(parts) + "."}


# ---------- Скрипты ----------

class ScriptBody(BaseModel):
    niche: int = Field(ge=0, le=99)
    kind: str = Field(pattern=r"^(first|short|detailed|call|followup)$")
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=4000)


@app.get("/api/scripts")
async def api_scripts(
    niche: int | None = Query(None, ge=0, le=99),
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    return {"scripts": await db.list_scripts(user["id"], niche), "kinds": scripts.KINDS}


@app.post("/api/scripts")
async def api_script_create(body: ScriptBody, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    script_id = await db.save_script(user["id"], body.niche, body.kind, body.title.strip(), body.body.strip())
    return {"ok": True, "id": script_id}


@app.put("/api/scripts/{script_id}")
async def api_script_update(
    script_id: int, body: ScriptBody, x_init_data: str | None = Header(None, alias="X-Init-Data")
):
    user = await current_user(x_init_data)
    current = await db.get_script(script_id)
    if not current:
        raise HTTPException(404, "Скрипт не найден.")
    if current["owner_id"] == 0:
        if is_admin(user):
            await db.save_script(0, current["niche"], body.kind, body.title.strip(), body.body.strip(), script_id)
            return {"ok": True, "id": script_id}
        # Обычный пользователь правит свою копию стандартного скрипта.
        new_id = await db.save_script(user["id"], current["niche"], body.kind, body.title.strip(), body.body.strip())
        return {"ok": True, "id": new_id, "copy": True}
    if current["owner_id"] != user["id"]:
        raise HTTPException(404, "Скрипт не найден.")
    await db.save_script(user["id"], current["niche"], body.kind, body.title.strip(), body.body.strip(), script_id)
    return {"ok": True, "id": script_id}


@app.delete("/api/scripts/{script_id}")
async def api_script_delete(script_id: int, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    current = await db.get_script(script_id)
    owner = 0 if (current and current["owner_id"] == 0 and is_admin(user)) else user["id"]
    if not await db.delete_script(owner, script_id):
        raise HTTPException(404, "Скрипт не найден.")
    return {"ok": True}


async def _ai_text(user_id: int, prompt: str) -> tuple[str, str]:
    """Возвращает (текст, причина отказа). Пустой текст = использовать шаблон."""
    if not AI_ENABLED:
        return "", "no_ai"
    if not await db.reserve_api_call(f"ai:{user_id}", AI_USER_DAILY_LIMIT, period="day"):
        return "", "user_limit"
    if not await db.reserve_api_call("ai", AI_DAILY_LIMIT, period="day"):
        return "", "global_limit"
    try:
        return await scripts.complete(prompt), ""
    except scripts.AIError as exc:
        await db.log_source_error("ai", str(exc))
        return "", "ai_error"


class GenerateRequest(BaseModel):
    niche: int = Field(ge=0, le=99)
    kind: str = Field(default="first", pattern=r"^(first|short|detailed|call|followup)$")
    custom: str = Field(default="", max_length=80)
    variant: int = Field(default=0, ge=0, le=1000)


@app.post("/api/scripts/generate")
async def api_script_generate(body: GenerateRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    text, note = await _ai_text(
        user["id"], scripts.niche_prompt(body.niche, body.kind, body.custom, body.variant)
    )
    if not text:
        defaults = [item for item in scripts.defaults() if item["niche"] == body.niche and item["kind"] == body.kind]
        base = defaults[0]["body"] if defaults else scripts.template_for_lead({}, body.kind)
        text = scripts.vary(base, body.variant if body.variant else 1)
    return {"text": text, "source": "ai" if not note else "template", "note": note}


class LeadScriptRequest(BaseModel):
    kind: str = Field(default="first", pattern=r"^(first|short|detailed|call|followup)$")
    variant: int = Field(default=0, ge=0, le=1000)


@app.post("/api/leads/{lead_id}/script")
async def api_lead_script(
    lead_id: int, body: LeadScriptRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")
):
    user = await current_user(x_init_data)
    lead = await db.user_lead(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Лид не найден.")
    text, note = await _ai_text(user["id"], scripts.lead_prompt(lead, body.kind, body.variant))
    if not text:
        text = scripts.template_for_lead(lead, body.kind, body.variant)
    return {"text": text, "source": "ai" if not note else "template", "note": note}


@app.post("/api/export")
async def api_export(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    task = asyncio.create_task(_export_after_response(user["id"]))
    WORKERS.add(task)
    task.add_done_callback(WORKERS.discard)
    return {"ok": True, "message": "Excel-файл придёт в чат с ботом."}


async def _export_after_response(user_id: int) -> None:
    try:
        from .export import send_export

        await send_export(user_id)
    except Exception:
        log.exception("Excel export failed for user %s", user_id)
        await _notify(user_id, "Не удалось подготовить Excel-файл. Попробуйте позже.")


# ---------- Админ-панель ----------

def _user_json(row: dict) -> dict:
    member = bool(row["approved"]) or bool(row["is_admin"])
    return {
        "id": row["id"],
        "n": "@" + row["username"] if row.get("username") else (row.get("first_name") or f"id{row['id']}"),
        "f": row.get("found", 0),
        "c": row.get("contacted", 0),
        "r": row.get("replied", 0),
        "k": row.get("clients", 0),
        "t": row.get("today", 0),
        "lim": row["daily_limit"],
        "approved": bool(row["approved"]),
        "is_admin": bool(row["is_admin"]),
        "banned": bool(row.get("banned")),
        "plan": "member" if member else "trial",
        "trial_used": row.get("trial_used", 0),
        "bonus": row.get("bonus", 0),
        "trial_left": None if member else db.trial_left(row, TRIAL_SEARCHES),
    }


@app.get("/api/admin/users")
async def admin_users(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"users": [_user_json(row) for row in await db.all_users_stats()]}


class LimitRequest(BaseModel):
    limit: int = Field(ge=0, le=5000)


@app.post("/api/admin/users/{user_id}/limit")
async def admin_limit(
    user_id: int,
    body: LimitRequest,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.set_limit(user_id, body.limit):
        raise HTTPException(404, "Пользователь не найден.")
    await _notify(user_id, f"<b>Лимит изменён</b>\n\nТеперь вам доступно <b>{body.limit}</b> лидов в день.")
    return {"ok": True}


class AccessRequest(BaseModel):
    approved: bool


@app.post("/api/admin/users/{user_id}/access")
async def admin_access(
    user_id: int,
    body: AccessRequest,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    require_admin(user)
    if user_id == user["id"]:
        raise HTTPException(400, "Нельзя закрыть собственный доступ владельца.")
    if user_id <= 0:
        raise HTTPException(400, "Telegram ID должен быть положительным числом.")
    if body.approved:
        await db.grant_member(user_id)
    elif not await db.set_approved(user_id, 0):
        raise HTTPException(404, "Пользователь не найден.")
    if body.approved:
        await _notify_access(user_id)
    else:
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
        await _notify(user_id, f"<b>Добавлены запросы</b>\n\nВам добавлено поисковых запросов: <b>{body.amount}</b>.\nОткройте Parser C&amp;C.")
    return {"ok": True, "bonus": bonus}


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
        raise HTTPException(422, "Ключ должен давать доступ или бонусные запросы.")
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
            "message": f"Лимит по умолчанию: {body.limit} лидов в день. {tail}"}


@app.delete("/api/admin/keys/{code}")
async def admin_key_delete(code: str, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.delete_key(code):
        raise HTTPException(404, "Ключ не найден.")
    return {"ok": True}


@app.get("/api/admin/leads")
async def admin_leads(
    q: str = Query("", max_length=80),
    offset: int = Query(0, ge=0),
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"leads": await db.admin_leads(q, 100, offset)}


@app.get("/api/admin/overview")
async def admin_overview(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    overview = await db.admin_overview()
    overview["errors"] = await db.source_errors(30)
    overview["api"] = {
        "google_month": await db.api_calls_this_month("google"),
        "dgis_month": await db.api_calls_this_month("dgis"),
        "geoapify_day": await db.api_calls_this_month("geoapify", "day"),
        "ai_day": await db.api_calls_this_month("ai", "day"),
    }
    return overview


class BlockRequest(BaseModel):
    lead_id: int | None = None
    text: str = Field(default="", max_length=200)


def _tokens_from_text(text: str) -> tuple[set[str], str]:
    value = text.strip()
    lead: dict = {"contacts": {}}
    if re.fullmatch(r"[+\d][\d\s()\-]{6,}", value):
        e164, pretty = cn.phone(value)
        if not e164 and value.lstrip("+").isdigit():
            e164 = "+" + value.lstrip("+")
        lead["phone"] = e164
        label = pretty or e164
    elif "@" in value and "." in value.split("@")[-1]:
        lead["contacts"]["email"] = cn.email(value)
        label = lead["contacts"]["email"]
    elif value.startswith("@") or "t.me/" in value:
        lead["contacts"]["tg"] = cn.telegram(value)
        label = lead["contacts"]["tg"]
    else:
        url = normalize_url(value)
        lead["site_url"] = url
        label = value
    tokens = {token for token in claim_tokens(lead) if not token.startswith("osm:")}
    return tokens, label


@app.get("/api/admin/blocked")
async def admin_blocked(x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    return {"items": await db.list_blocked()}


@app.post("/api/admin/blocked")
async def admin_block(body: BlockRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if body.lead_id:
        lead = await db.lead_by_id(body.lead_id)
        if not lead:
            raise HTTPException(404, "Лид не найден.")
        tokens = claim_tokens(lead)
        label = f"{lead['name']} · {lead['city']}"
    else:
        tokens, label = _tokens_from_text(body.text)
    if not tokens:
        raise HTTPException(422, "Укажите телефон, сайт, email или @telegram бизнеса.")
    await db.block_tokens(tokens, label)
    return {"ok": True, "label": label}


class UnblockRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)


@app.post("/api/admin/unblock")
async def admin_unblock(body: UnblockRequest, x_init_data: str | None = Header(None, alias="X-Init-Data")):
    user = await current_user(x_init_data)
    require_admin(user)
    if not await db.unblock(body.label):
        raise HTTPException(404, "Запись не найдена.")
    return {"ok": True}


@app.get("/api/admin/members")
async def admin_members(
    q: str = Query("", max_length=64),
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    """Все, кто запускал бота: юзернейм, ID и открывал ли мини‑апп."""
    user = await current_user(x_init_data)
    require_admin(user)
    items = await db.members(q)
    return {
        "members": items,
        "total": len(items),
        "opened": sum(1 for item in items if item["app_opened"]),
    }


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
    raw = base64.b64decode(match.group(2))
    if len(raw) > 5_000_000:
        raise HTTPException(422, "Картинка больше 5 МБ.")
    return raw


async def _run_broadcast(admin_id: int, message: str, image: bytes | None) -> None:
    try:
        from .bot import broadcast_to_approved

        sent, total = await broadcast_to_approved(message, image=image)
        await _notify(admin_id, f"<b>Рассылка завершена</b>\n\nДоставлено: <b>{sent}</b> из {total}.")
    except Exception:
        log.exception("Broadcast failed")
        await _notify(admin_id, "Рассылку не удалось завершить.")


@app.post("/api/admin/broadcast")
async def admin_broadcast(
    body: BroadcastRequest,
    x_init_data: str | None = Header(None, alias="X-Init-Data"),
):
    user = await current_user(x_init_data)
    require_admin(user)
    message = telegram_html(body.text.strip())
    image = _decode_image(body.image)
    if not message and not image:
        raise HTTPException(422, "Добавьте текст или картинку.")
    if len(re.sub(r"<[^>]+>", "", message)) > 4000:
        raise HTTPException(422, "Текст длиннее 4000 символов.")
    task = asyncio.create_task(_run_broadcast(user["id"], message, image))
    WORKERS.add(task)
    task.add_done_callback(WORKERS.discard)
    return {"ok": True, "message": "Рассылка запущена. Результат придёт в чат с ботом."}


static_dir = Path(ROOT_DIR) / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="miniapp")
