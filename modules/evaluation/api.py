"""API мини-аппа: только для админов. Очередь заявок, оценка, переписка, люди и баланс."""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from . import db
from . import render
from . import texts
from .auth import verify_init_data

log = logging.getLogger("evaluation.api")
app = FastAPI(title="Evaluation C&C", docs_url=None, redoc_url=None, openapi_url=None)


async def current_admin(init_data: str | None) -> dict:
    user = verify_init_data(init_data or "")
    if not user:
        raise HTTPException(401, "Откройте мини-апп через бота в Telegram.")
    if not config.is_admin_user(user.get("id"), user.get("username")):
        raise HTTPException(403, "Мини-апп только для админов Evaluation C&C.")
    await db.upsert_user(user["id"], user.get("username"), user.get("first_name"))
    user["name"] = render.user_name(user)
    return user


@app.middleware("http")
async def fresh_static(request, call_next):
    """Telegram на телефоне любит кешировать мини-апп — просим всегда сверяться с сервером."""
    started = time.monotonic()
    path = request.url.path
    response = await call_next(request)
    if path.startswith("/api/") and "/media/" not in path and path != "/api/ping":
        # видно в railway logs: дошёл ли запрос с телефона и что ответили
        log.info("%s %s -> %s за %d мс", request.method, path, response.status_code, (time.monotonic() - started) * 1000)
    if not path.startswith("/api/") and (path.endswith((".html", ".js")) or path == "/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/api/ping")
async def ping(request: Request, id: str = "", s: str = "", t: int = 0):
    """Отметки с телефона: что успела сделать страница (видно в railway logs)."""
    ua = (request.headers.get("user-agent") or "")[:90]
    log.info("PING %s %s [%d мс] %s", id[:8], s[:120], t, ua)
    return Response(status_code=204)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/me")
async def me(x_init_data: str | None = Header(None)):
    user = await current_admin(x_init_data)
    return {
        "id": user["id"], "name": user["name"], "brand": config.BRAND,
        "criteria": [{"key": k, "title": t} for k, t in db.CRITERIA],
        "free": config.FREE_REVIEWS, "price": config.PRICE_RUB, "stars": config.PRICE_STARS,
        "paid": config.PAID_ENABLED,
    }


def public_review(r: dict, full: bool = False) -> dict:
    item = {
        "id": r["id"], "status": r["status"], "kind": r["kind"], "url": r.get("url") or "",
        "comment": r.get("comment") or "", "user_id": r["user_id"],
        "user": render.user_name({"username": r.get("username"), "first_name": r.get("first_name"), "id": r["user_id"]}),
        "media": [{"type": m.get("type"), "size": m.get("size") or 0, "mime": m.get("mime") or ""} for m in r.get("media") or []],
        "admin_id": r.get("admin_id"), "admin_name": r.get("admin_name") or "",
        "scores": r.get("scores") or {}, "notes": r.get("notes") or {}, "total": r.get("total"),
        "pros": r.get("pros") or "", "cons": r.get("cons") or "", "advice": r.get("advice") or "",
        "body": r.get("body") or "", "reason": r.get("reason") or "", "created_at": r["created_at"], "done_at": r.get("done_at"),
        "msg_count": r.get("msg_count", 0),
    }
    if full:
        item["messages"] = [{"id": m["id"], "from_admin": bool(m["from_admin"]), "text": m["text"],
                             "created_at": m["created_at"]} for m in r.get("messages") or []]
    return item


@app.get("/api/reviews")
async def reviews(status: str = Query("open", pattern=r"^(open|new|work|done|rejected|all)$"),
                  q: str = Query("", max_length=80), x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    return {"items": [public_review(r) for r in await db.list_reviews(status, q)]}


async def load_review(review_id: int) -> dict:
    review = await db.get_review(review_id)
    if not review:
        raise HTTPException(404, "Заявка не найдена.")
    return review


@app.get("/api/reviews/{review_id}")
async def review(review_id: int, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    r = await load_review(review_id)
    data = public_review(r, full=True)
    data["preview"] = render.review_result(r) if r["status"] == "done" else ""
    return data


@app.get("/api/reviews/{review_id}/media/{index}")
async def media(review_id: int, index: int, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    r = await load_review(review_id)
    items = r.get("media") or []
    if not 0 <= index < len(items):
        raise HTTPException(404, "Файл не найден.")
    item = items[index]
    if (item.get("size") or 0) > 20 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 20 МБ — Telegram не отдаёт его в мини-апп. Нажмите «Прислать в чат».")
    from .bot import download_media

    try:
        data = await download_media(item["file_id"])
    except Exception as exc:  # noqa: BLE001 — любая ошибка Telegram превращается в понятный ответ
        log.warning("Media download failed: %s", exc)
        raise HTTPException(502, "Не удалось получить файл из Telegram. Нажмите «Прислать в чат».")
    mime = item.get("mime") or ("image/jpeg" if item.get("type") == "photo" else "video/mp4")
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/reviews/{review_id}/forward")
async def forward(review_id: int, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    r = await load_review(review_id)
    from .bot import send_media

    await send_media(admin["id"], r.get("media") or [])
    return {"ok": True, "message": "Файлы отправлены вам в чат с ботом."}


@app.post("/api/reviews/{review_id}/take")
async def take(review_id: int, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    r = await db.take_review(review_id, admin["id"], admin["name"])
    if not r:
        raise HTTPException(409, "Заявку уже взяли или она закрыта.")
    from .bot import notify_taken

    await notify_taken(r, admin["name"], admin["id"])
    return {"ok": True}


class RateBody(BaseModel):
    text: str = Field(default="", max_length=12000)  # главный текст оценки (HTML Telegram)
    scores: dict[str, float] = Field(default_factory=dict)  # баллы — по желанию
    notes: dict[str, str] = Field(default_factory=dict)
    pros: str = Field(default="", max_length=1200)
    cons: str = Field(default="", max_length=1200)
    advice: str = Field(default="", max_length=1200)


@app.post("/api/reviews/{review_id}/rate")
async def rate(review_id: int, body: RateBody, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    scores = {}
    given = {k: v for k, v in (body.scores or {}).items() if k in db.CRITERIA_KEYS and v is not None}
    if given and len(given) != len(db.CRITERIA_KEYS):
        raise HTTPException(422, "Баллы — по желанию, но если ставишь, то всем пяти пунктам.")
    for key, value in given.items():
        value = float(value)
        if not 1 <= value <= 10 or round(value * 2) != value * 2:
            raise HTTPException(422, "Балл — от 1 до 10, можно с половинкой.")
        scores[key] = value
    notes = {k: str(v).strip()[:600] for k, v in (body.notes or {}).items() if k in db.CRITERIA_KEYS and str(v).strip()}
    text = texts.telegram_html(body.text)
    if texts.plain_len(text) > 3300:
        raise HTTPException(422, "Текст длинноват для одного сообщения Telegram — сократи до 3300 знаков.")
    if not (texts.plain_len(text) >= 3 or body.pros.strip() or body.cons.strip() or body.advice.strip() or notes):
        raise HTTPException(422, "Напиши текст оценки.")
    total = round(sum(scores.values()) / len(scores), 1) if scores else None
    ok = await db.finish_review(review_id, admin["id"], admin["name"], scores, total,
                                body.pros.strip(), body.cons.strip(), body.advice.strip(), notes, text)
    if not ok:
        raise HTTPException(409, "Заявка уже закрыта.")
    r = await db.get_review(review_id)
    from .bot import notify_other_admins, send_result

    delivered = await send_result(r)
    await notify_other_admins(admin["id"], f"{render.esc(admin['name'])} оценил заявку #{review_id}: "
                                           + (f"<b>{render.fmt_score(total)}/10</b>." if total is not None else "текстом."), review_id)
    return {"ok": True, "total": total, "delivered": delivered,
            "message": "Оценка отправлена." if delivered else "Оценка сохранена, но человек остановил бота — не доставлено."}


class RejectBody(BaseModel):
    reason: str = Field(default="", max_length=600)


@app.post("/api/reviews/{review_id}/reject")
async def reject(review_id: int, body: RejectBody, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    r = await db.reject_review(review_id, admin["id"], admin["name"], body.reason.strip())
    if not r:
        raise HTTPException(409, "Заявка уже закрыта.")
    from .bot import send_rejected

    await send_rejected(r, body.reason.strip())
    return {"ok": True, "message": "Заявка отклонена, оценка вернулась человеку на баланс."}


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=3500)


@app.post("/api/reviews/{review_id}/message")
async def message(review_id: int, body: MessageBody, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    r = await load_review(review_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Пустое сообщение.")
    await db.add_message(review_id, admin["id"], True, text)
    from .bot import send_admin_message

    delivered = await send_admin_message(r, text, admin["name"])
    return {"ok": True, "delivered": delivered,
            "message": "Отправлено." if delivered else "Сохранено, но человек остановил бота — не доставлено."}


@app.get("/api/users")
async def users(q: str = Query("", max_length=80), x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    items = await db.list_users(q)
    return {"items": [{
        "id": u["id"], "name": render.user_name(u), "first_name": u.get("first_name") or "",
        "free_left": u["free_left"], "credits": u["credits"], "reviews": u["reviews"], "paid": u["paid"],
        "banned": bool(u["banned"]), "admin": config.is_admin_user(u["id"], u.get("username")),
        "created_at": u["created_at"],
    } for u in items]}


class CreditsBody(BaseModel):
    amount: int = Field(ge=-100, le=100)


@app.post("/api/users/{user_id}/credits")
async def credits(user_id: int, body: CreditsBody, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    if body.amount == 0:
        raise HTTPException(422, "Укажите, сколько оценок добавить.")
    if not await db.get_user(user_id):
        raise HTTPException(404, "Человек ещё не запускал бота.")
    total = await db.add_credits(user_id, body.amount, admin["id"])
    if body.amount > 0:
        from .bot import notify_credits

        await notify_credits(user_id, body.amount, total)
    return {"ok": True, "credits": total}


class BanBody(BaseModel):
    banned: bool


@app.post("/api/users/{user_id}/ban")
async def ban(user_id: int, body: BanBody, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    target = await db.get_user(user_id)
    if not target:
        raise HTTPException(404, "Человек не найден.")
    if config.is_admin_user(user_id, target.get("username")):
        raise HTTPException(422, "Админа забанить нельзя.")
    await db.set_banned(user_id, body.banned)
    return {"ok": True}


@app.get("/api/overview")
async def overview(x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    return await db.overview()


@app.get("/api/stats")
async def stats(x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    return {"overview": await db.overview(), "daily": await db.daily(14)}


# ---------- Сообщения (тексты бота) ----------

@app.get("/api/texts")
async def list_texts(x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    saved = await db.all_texts()
    items = []
    for key, meta in texts.DEFAULTS.items():
        if meta.get("paid") and not config.PAID_ENABLED:
            continue  # тексты оплаты скрыты, пока платные оценки выключены
        row = saved.get(key)
        items.append({
            "key": key, "group": meta["group"], "title": meta["title"],
            "vars": [{"key": v, "title": texts.VAR_TITLES.get(v, v)} for v in meta["vars"]],
            "text": row["text"] if row else meta["text"], "default": meta["text"],
            "changed": bool(row), "has_image": bool(row and row["has_image"]),
        })
    return {"groups": list(texts.GROUPS), "items": items}


@app.get("/api/texts/{key}/image")
async def text_image(key: str, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    image = await db.get_text_image(key)
    if not image:
        raise HTTPException(404, "Картинки нет.")
    return Response(content=image, media_type="image/jpeg")


def decode_image(data_url: str) -> bytes:
    match = re.fullmatch(r"data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\s]+)", (data_url or "").strip())
    if not match:
        raise HTTPException(422, "Картинка должна быть JPG, PNG или WEBP.")
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", match.group(2)) + "==")
    except (ValueError, TypeError):
        raise HTTPException(422, "Картинка повреждена, выберите другую.")
    if not raw:
        raise HTTPException(422, "Картинка повреждена, выберите другую.")
    if len(raw) > 5_000_000:
        raise HTTPException(422, "Картинка больше 5 МБ.")
    return raw


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    image: str = Field(default="keep", max_length=8_000_000)  # keep | none | data:image/...


@app.put("/api/texts/{key}")
async def save_text(key: str, body: TextBody, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    if key not in texts.DEFAULTS:
        raise HTTPException(404, "Такого сообщения нет.")
    text = texts.telegram_html(body.text)
    if not text:
        raise HTTPException(422, "Текст пустой.")
    if texts.plain_len(text) > 4000:
        raise HTTPException(422, "Текст длиннее 4000 символов — Telegram его не отправит.")
    keep = body.image == "keep"
    image = None if keep or body.image == "none" else decode_image(body.image)
    await db.set_text(key, text, image, keep_image=keep)
    return {"ok": True, "text": text}


@app.delete("/api/texts/{key}")
async def reset_text(key: str, x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    if key not in texts.DEFAULTS:
        raise HTTPException(404, "Такого сообщения нет.")
    await db.reset_text(key)
    return {"ok": True}


@app.post("/api/texts/{key}/test")
async def test_text(key: str, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    if key not in texts.DEFAULTS:
        raise HTTPException(404, "Такого сообщения нет.")
    from .bot import say

    sample = {"name": render.esc(admin.get("first_name") or "друг"), "free": config.FREE_REVIEWS, "price": config.PRICE_RUB,
              "stars": config.PRICE_STARS, "balance": "Доступно: бесплатных — <b>2</b>.", "id": 123,
              "admin": render.esc(admin["name"]), "reason": "<blockquote>Пример причины</blockquote>",
              "contact": "@" + config.PAY_CONTACT}
    ok = await say(admin["id"], key, **sample)
    return {"ok": ok, "message": "Пример отправлен вам в чат с ботом." if ok else "Не получилось отправить — откройте бота и нажмите /start."}


# ---------- Рассылка ----------

@app.get("/api/broadcast")
async def broadcast_info(x_init_data: str | None = Header(None)):
    await current_admin(x_init_data)
    return {"segments": await db.segment_counts()}


class BroadcastBody(BaseModel):
    text: str = Field(default="", max_length=8000)
    images: list[str] = Field(default_factory=list, max_length=10)
    segment: str = Field(default="all", pattern=r"^(all|sent|not_sent|paid)$")


BROADCAST_TASKS: set = set()


@app.post("/api/broadcast")
async def broadcast(body: BroadcastBody, x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    text = texts.telegram_html(body.text) if body.text.strip() else ""
    images = [decode_image(item) for item in body.images]
    if not text and not images:
        raise HTTPException(422, "Добавьте текст или фото.")
    if texts.plain_len(text) > 4000:
        raise HTTPException(422, "Текст длиннее 4000 символов.")
    ids = await db.segment_ids(body.segment)
    if not ids:
        raise HTTPException(422, "В этой группе никого нет.")
    from .bot import broadcast as run, safe_send

    async def job():
        try:
            sent, total = await run(text, images, ids)
            await safe_send(admin["id"], f"<b>Рассылка завершена</b>\n\nДоставлено: <b>{sent}</b> из {total}.")
        except Exception:
            log.exception("Broadcast failed")
            await safe_send(admin["id"], "Рассылку не удалось завершить.")

    task = asyncio.create_task(job())
    BROADCAST_TASKS.add(task)
    task.add_done_callback(BROADCAST_TASKS.discard)
    return {"ok": True, "total": len(ids), "message": f"Рассылка запущена: {len(ids)} чел. Итог придёт в чат с ботом."}


# ---------- Предпросмотр: как всё видит участник ----------

SAMPLE_REVIEW = {
    "id": 128, "url": "https://barber-kzn.ru", "admin_name": "@fuckprincov", "total": None, "scores": {},
    "body": ("<b>Дизайн</b>\nЧистый первый экран, приятные фото мастеров. Но фото тёмные — на телефоне почти ничего не видно.\n\n"
             "<b>Удобство</b>\nКнопка «Записаться» есть, но на телефоне уезжает вниз — её легко не заметить.\n\n"
             "<b>Что сделать первым</b>\n<blockquote>1. Закрепить кнопку записи внизу экрана.\n2. Добавить 3–4 отзыва с фото.\n"
             "3. Убрать лишние пункты из меню.</blockquote>"),
}
SAMPLE_SCORES = {"design": 8, "ux": 7, "mobile": 6.5, "text": 7, "trust": 8.5}


def sample_values(admin: dict) -> dict:
    return {
        "name": "Тимур", "free": config.FREE_REVIEWS, "price": config.PRICE_RUB, "stars": config.PRICE_STARS,
        "balance": "Доступно: бесплатных — <b>2</b>.", "id": SAMPLE_REVIEW["id"], "admin": render.esc(admin["name"]),
        "reason": "<blockquote>На скриншотах не видно сайта — пришли, пожалуйста, другие.</blockquote>",
        "contact": "@" + config.PAY_CONTACT,
    }


@app.get("/api/preview")
async def preview(x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    values = sample_values(admin)
    from .bot import draft_text

    async def bot_text(key: str, buttons: list[str] | None = None, note: str = "") -> dict:
        raw, image, _changed = await db.get_text(key)
        return {"who": "bot", "key": key, "html": texts.fill(raw, values), "image": bool(image),
                "buttons": buttons or [], "note": note}

    welcome_buttons = ["Отправить сайт на оценку", "Мои оценки"] + (["Купить оценку"] if config.PAID_ENABLED else [])
    outro, _img, _ch = await db.get_text("result_outro")
    review = dict(SAMPLE_REVIEW, admin_name=admin["name"])
    draft = {"media": [{}, {}, {}], "url": "barber-kzn.ru", "comment": "Посмотрите, пожалуйста, мобильную версию"}
    steps = [
        {"who": "user", "html": "/start"},
        await bot_text("welcome", welcome_buttons, "Первое сообщение после /start"),
        {"who": "tap", "html": "Отправить сайт на оценку"},
        await bot_text("how", [], "После кнопки «Отправить сайт на оценку»"),
        {"who": "user", "kind": "photos", "count": 3, "html": "barber-kzn.ru\nПосмотрите, пожалуйста, мобильную версию"},
        {"who": "bot", "html": draft_text(draft, {"free_used": 0}), "buttons": ["Отправить на оценку", "Очистить"],
         "note": "Черновик — собирается сам, пока человек присылает файлы"},
        {"who": "tap", "html": "Отправить на оценку"},
        await bot_text("accepted", ["Мои оценки"], "Заявка ушла админам"),
        await bot_text("taken", [], "Когда админ взял заявку в работу"),
        {"who": "bot", "html": render.review_result(review, texts.fill(outro, {})), "key": "result_outro",
         "buttons": ["Ответить", "Оценить ещё сайт"], "note": "Оценка — то, что админ написал текстом. Подпись внизу меняется в «Сообщениях»"},
        {"who": "bot", "kind": "card", "html": f"<b>{render.esc(config.BRAND)}</b> · заявка #{review['id']}",
         "note": "Если админ поставил ещё и баллы — перед текстом придёт такая картинка"},
        {"who": "bot", "html": render.admin_message(review["id"], "Если пришлёте вид с телефона, подскажу точнее по меню.", admin["name"]),
         "buttons": ["Ответить"], "note": "Когда админ пишет человеку из мини-аппа"},
        await bot_text("limit", [], "Когда бесплатные оценки закончились") if not config.PAID_ENABLED
        else await bot_text("pay_offer", [], "Когда бесплатные оценки закончились"),
        await bot_text("rejected", ["Отправить заново"], "Если заявку отклонили (оценка возвращается)"),
    ]
    return {"steps": steps, "values": values}


@app.get("/api/preview/card")
async def preview_card(x_init_data: str | None = Header(None)):
    admin = await current_admin(x_init_data)
    from . import card

    sample = dict(SAMPLE_REVIEW, admin_name=admin["name"], scores=SAMPLE_SCORES,
                  total=round(sum(SAMPLE_SCORES.values()) / len(SAMPLE_SCORES), 1))
    png = card.render_card(sample, config.BRAND)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


STATIC = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC, html=True), name="miniapp")
