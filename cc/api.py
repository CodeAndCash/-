"""Сервер C&C Family: API мини-аппа, админка, оплата. Парсер, скрипты и админка оценок — по своим адресам."""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BufferedInputFile, InputMediaDocument, InputMediaPhoto, InputMediaVideo,
)
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import access, ai_review, config, content, db, payments, texts
from .auth import verify_init_data
from .tg import bot

log = logging.getLogger("cc.api")
WEB_DIR = config.ROOT_DIR / "web"
WORKERS: set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    WORKERS.add(task)
    task.add_done_callback(WORKERS.discard)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from modules.evaluation import db as eval_db
    from modules.parser import api as parser_api
    from .content_seed import ITEMS, RETIRED

    await db.init()
    added = await db.seed_content(ITEMS, RETIRED)
    if added:
        log.info("Добавлено стартовых материалов: %s", added)
    await eval_db.init()
    async with AsyncExitStack() as stack:
        # У вложенных приложений свой запуск не срабатывает — запускаем вручную.
        await stack.enter_async_context(parser_api.lifespan(parser_api.app))
        yield
    for task in list(WORKERS):
        task.cancel()


app = FastAPI(title="C&C Family", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or "/api/" in path:
        response.headers["Cache-Control"] = "no-store, private"
    elif path == "/" or path.endswith((".html", "/")):
        response.headers["Cache-Control"] = "no-cache"
    elif request.query_params.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ---------- Вход ----------

async def current_user(init_data: str | None) -> dict:
    tg_user = verify_init_data(init_data or "")
    if not tg_user:
        raise HTTPException(401, "Не удалось проверить вход Telegram. Закрой приложение и открой снова.")
    user = await db.upsert_user(tg_user["id"], tg_user.get("username"), tg_user.get("first_name"),
                                tg_user.get("last_name"), tg_user.get("photo_url"))
    if user.get("banned") and not is_admin(user):
        raise HTTPException(403, {"code": "banned", "message": "Доступ закрыт. Если это ошибка, напиши в поддержку.",
                                  "support": config.SUPPORT_USERNAME})
    return user


def is_admin(user: dict) -> bool:
    return config.is_admin_user(user["id"], user.get("username"))


async def admin_user(init_data: str | None) -> dict:
    user = await current_user(init_data)
    if not is_admin(user):
        raise HTTPException(403, "Только для админов.")
    return user


InitData = Header(None, alias="X-Init-Data")


def access_info(user: dict) -> dict:
    resident = db.is_resident(user)
    return {
        "resident": resident,
        "forever": bool(user.get("access_forever")),
        "until": int(user.get("access_until") or 0) if db.has_paid_access(user) else 0,
        "tariff": user.get("tariff") or "",
        "group": bool(user.get("group_member")),
        "admin": is_admin(user),
    }


async def tariffs_public() -> list[dict]:
    out = []
    for t in await access.tariffs():
        item = {k: t.get(k) for k in ("id", "title", "subtitle", "price", "price_usd", "days", "badge", "features",
                                      "note", "stars", "mentor")}
        item["active"] = bool(t.get("active"))
        item["card"] = bool(t.get("tribute_link") or config.PAYMENT_PROVIDER_TOKEN)
        item["weekly_seats"] = int(t.get("weekly_seats") or 0)
        left = await access.seats_left(t) if t.get("active") else 0
        item["seats_left"] = left if item["weekly_seats"] else 0
        item["available"] = item["active"] and (not item["weekly_seats"] or left > 0)
        out.append(item)
    return out


async def module_counts() -> dict:
    from modules.parser import countries, niches

    return {"niches": len(niches.public_list()), "countries": len(countries.public_list())}


@app.get("/api/bootstrap")
async def bootstrap(x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    if config.GROUP_ID and not db.has_paid_access(user):
        try:
            user = await asyncio.wait_for(access.refresh_group(user), timeout=3)
        except asyncio.TimeoutError:
            pass
    await db.log_event(user["id"], "open")
    gate = None
    if not await access.channel_ok(user):
        gate = {"link": config.CHANNEL_LINK, "name": config.CHANNEL_NAME}
    lessons = await content.listing("lesson", user)
    reviews = [{"name": r["title"], "role": r["subtitle"], "text": r["body"]}
               for r in await db.list_content("review")]
    return {
        "me": {
            "id": user["id"], "name": user.get("first_name") or user.get("username") or "друг",
            "last_name": user.get("last_name") or "", "username": user.get("username") or "",
            "photo": user.get("photo_url") or "", "notify": bool(user.get("notify")), "theme": user.get("theme") or "",
            "lang": user.get("lang") or "", "access": access_info(user),
        },
        "gate": gate,
        "compare": await access.compare_rows(),
        "community": {"members": await access.members_count(), "title": config.BRAND},
        "tariffs": await tariffs_public(),
        "methods": payments.methods(),
        "card_link": await card_link(),
        "counts": {**await content.counts(), **await module_counts()},
        "lessons": lessons,
        "picks": await content.listing("resource", user),
        "marathon": await content.marathon_state(user["id"], user),
        "reviews": reviews,
        "links": {"support": config.SUPPORT_USERNAME, "personal": config.PERSONAL_USERNAME,
                  "bot": config.BOT_USERNAME, "group": config.GROUP_LINK if db.is_resident(user) else "",
                  "chat": config.CHAT_LINK if db.is_resident(user) else ""},
        "version": config.APP_VERSION,
    }


class Prefs(BaseModel):
    notify: bool | None = None
    theme: str | None = Field(default=None, pattern=r"^(light|dark|)$")
    lang: str | None = Field(default=None, pattern=r"^(ru|uk|en|kk|be|az|tg|)$")


@app.post("/api/prefs")
async def prefs(body: Prefs, x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    fields = {}
    if body.notify is not None:
        fields["notify"] = int(body.notify)
    if body.theme is not None:
        fields["theme"] = body.theme
    if body.lang is not None:
        fields["lang"] = body.lang
    if fields:
        await db.update_user(user["id"], **fields)
    return {"ok": True}


@app.post("/api/gate/check")
async def gate_check(x_init_data: str | None = InitData):
    """«Я подписался» в приложении: проверяем канал заново."""
    user = await current_user(x_init_data)
    ok = await access.channel_ok(user, force=True)
    return {"ok": ok, "message": "Подписку вижу, добро пожаловать" if ok else
            "Пока не вижу подписки или заявки. Подай заявку в канал и нажми «Проверить» ещё раз."}


# ---------- Материалы ----------

@app.get("/api/content")
async def content_list(kind: str, x_init_data: str | None = InitData):
    if kind not in content.KINDS:
        raise HTTPException(404, "Нет такого раздела.")
    user = await current_user(x_init_data)
    return {"items": await content.listing(kind, user)}


@app.get("/api/content/{cid}")
async def content_item(cid: int, x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    item = await content.detail(cid, user)
    if not item:
        raise HTTPException(404, "Материал не найден или снят с публикации.")
    return item


class Done(BaseModel):
    done: bool = True


@app.post("/api/content/{cid}/done")
async def content_done(cid: int, body: Done, x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    item = await content.detail(cid, user)
    if not item or item.get("locked"):
        raise HTTPException(403, "Этот материал пока закрыт.")
    await db.set_done(user["id"], cid, body.done)
    state = await content.marathon_state(user["id"], user) if item["kind"] == "marathon" else None
    return {"ok": True, "done": body.done, "marathon": state}


@app.get("/api/marathon")
async def marathon(x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    return await content.marathon_state(user["id"], user)


# ---------- Оплата ----------

class Checkout(BaseModel):
    tariff: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    method: str = Field(pattern=r"^(card|cardlink|crypto|xrocket|stars)$")


@app.post("/api/checkout")
async def checkout(body: Checkout, x_init_data: str | None = InitData):
    user = await current_user(x_init_data)
    await db.log_event(user["id"], "pay_click", f"{body.tariff}:{body.method}")
    tariff = await access.tariff(body.tariff)
    if not tariff:
        raise HTTPException(404, "Нет такого тарифа.")
    if not tariff.get("active"):
        raise HTTPException(409, "Этот тариф скоро откроется.")
    if int(tariff.get("weekly_seats") or 0) and await access.seats_left(tariff) <= 0:
        raise HTTPException(409, "Места на эту неделю закончились. Следующий набор — в понедельник.")
    if body.method == "cardlink":
        # Карта через менеджера: открываем чат по ссылке, доступ выдаёт админ после оплаты.
        link = await card_link()
        if not link:
            raise HTTPException(409, "Оплата картой пока не настроена. Напиши в поддержку — поможем оплатить.")
        pid = await db.create_payment(user["id"], tariff["id"], "cardlink", float(tariff["price"]), "RUB",
                                      int(tariff.get("days") or 0))
        await db.set_payment_link(pid, "", link)
        await db.log_event(user["id"], "checkout", f"{tariff['id']}:cardlink")
        from .bot import notify_card_request
        spawn(notify_card_request(user, tariff, pid))
        return {"payment": pid, "kind": "manual", "url": link}
    if body.method not in payments.methods():
        raise HTTPException(409, "Этот способ оплаты пока не подключён. Напиши в поддержку — поможем оплатить.")
    stars = body.method == "stars"
    rocket = body.method == "xrocket"
    amount = (float(tariff.get("stars") or 0) if stars else float(tariff.get("price_usd") or 0) if rocket
              else float(tariff["price"]))
    if amount <= 0:
        raise HTTPException(409, "Для этого тарифа не указана цена в $. Напиши в поддержку." if rocket else
                            "Для этого тарифа не указана цена. Напиши в поддержку.")
    days = int(tariff.get("days") or 0)
    if body.method == "card" and tariff.get("tribute_link"):
        # Карта через Tribute: открываем товар в Tribute, доступ откроет вебхук.
        pid = await db.create_payment(user["id"], tariff["id"], "tribute", amount, "RUB", days)
        await db.set_payment_link(pid, "", tariff["tribute_link"])
        await db.log_event(user["id"], "checkout", f"{tariff['id']}:tribute")
        return {"payment": pid, "kind": "link", "url": tariff["tribute_link"]}
    if body.method == "card" and not config.PAYMENT_PROVIDER_TOKEN:
        raise HTTPException(409, "Оплата картой для этого тарифа ещё не настроена. Напиши в поддержку — поможем оплатить.")
    currency = "XTR" if stars else config.XROCKET_CURRENCY if rocket else "RUB"
    pid = await db.create_payment(user["id"], tariff["id"], body.method, amount, currency, days)
    payment = await db.get_payment(pid)
    title = f"{tariff['title']}" + (" · навсегда" if days == 0 else f" · {days} дн.")
    try:
        if body.method == "crypto":
            invoice_id, url = await payments.crypto_invoice(payment, title)
            await db.set_payment_link(pid, invoice_id, url)
            result = {"kind": "link", "url": url}
        elif rocket:
            invoice_id, url = await payments.xrocket_invoice(payment, title)
            await db.set_payment_link(pid, invoice_id, url)
            result = {"kind": "link", "url": url}
        else:
            link = await payments.telegram_invoice_link(
                payment, f"C&C Family · {tariff['title']}", tariff.get("subtitle") or "Доступ к C&C Family")
            await db.set_payment_link(pid, "", link)
            result = {"kind": "invoice", "url": link}
    except Exception as exc:
        log.exception("Не удалось создать счёт (%s)", body.method)
        await db.set_payment_status(pid, "cancelled")
        detail = "Платёжка не ответила. Попробуй ещё раз или напиши в поддержку."
        if is_admin(user):  # админу показываем настоящую причину, чтобы было что чинить
            detail += f" Причина: {exc}"
        raise HTTPException(502, detail) from exc
    await db.log_event(user["id"], "checkout", f"{tariff['id']}:{body.method}")
    return {"payment": pid, **result}


async def check_crypto(payment_list: list[dict]) -> int:
    """Сверяет счета Crypto Pay. Возвращает, сколько оплат зачтено."""
    from .bot import complete_payment

    ids = [p["external_id"] for p in payment_list if p["external_id"]]
    if not ids or not config.CRYPTO_PAY_TOKEN:
        return 0
    statuses = await payments.crypto_paid_ids(ids)
    done = 0
    for p in payment_list:
        status = statuses.get(p["external_id"])
        if status == "paid":
            done += int(await complete_payment(p, note=f"crypto:{p['external_id']}"))
        elif status == "expired":
            await db.set_payment_status(p["id"], "expired")
    return done


async def check_xrocket(payment_list: list[dict]) -> int:
    """Сверяет счета xRocket по одному. Возвращает, сколько оплат зачтено."""
    from .bot import complete_payment

    if not config.XROCKET_PAY_TOKEN:
        return 0
    done = 0
    for p in payment_list:
        if not p["external_id"]:
            continue
        try:
            status = await payments.xrocket_status(p["external_id"])
        except Exception:
            log.info("xRocket: не удалось проверить счёт %s", p["external_id"])
            continue
        if status == "paid":
            done += int(await complete_payment(p, note=f"xrocket:{p['external_id']}"))
        elif status == "expired":
            await db.set_payment_status(p["id"], "expired")
    return done


@app.post("/api/access/check")
async def access_check(x_init_data: str | None = InitData):
    """«Я уже оплатил / Проверить доступ»: сверяем крипту и участие в закрытой группе."""
    user = await current_user(x_init_data)
    mine = [p for p in await db.pending_payments("crypto", newer_than=int(time.time()) - 86400)
            if p["user_id"] == user["id"]]
    try:
        await check_crypto(mine)
    except Exception:
        log.exception("Сверка крипты не удалась")
    rockets = [p for p in await db.pending_payments("xrocket", newer_than=int(time.time()) - 86400)
               if p["user_id"] == user["id"]]
    await check_xrocket(rockets)
    user = await db.get_user(user["id"])
    user = await access.refresh_group(user, force=True)
    await access.sync_modules(user)
    info = access_info(user)
    if info["resident"]:
        message = "Доступ открыт, всё на месте."
    elif not config.GROUP_ID:
        message = "Оплату пока не видим. Если платил, напиши в поддержку — проверим вручную."
    else:
        message = "Не нашли тебя в закрытой группе и оплату пока не видим. Если платил — напиши в поддержку."
    return {"access": info, "message": message}


@app.post("/api/pay/crypto")
async def crypto_webhook(request: Request):
    """Уведомления Crypto Pay (адрес вписывается в @CryptoBot → Crypto Pay → Webhooks)."""
    from .bot import complete_payment

    body = await request.body()
    if not payments.crypto_signature_ok(body, request.headers.get("crypto-pay-api-signature", "")):
        raise HTTPException(401, "bad signature")
    parsed = payments.parse_crypto_update(body)
    if parsed and parsed[1] == "paid":
        payment = await db.payment_by_external("crypto", parsed[0])
        if payment:
            await complete_payment(payment, note=f"crypto:{parsed[0]}")
    return {"ok": True}


@app.post("/api/pay/xrocket")
async def xrocket_webhook(request: Request):
    """Уведомления xRocket (адрес вписывается в @xrocket → Rocket Pay → касса → Webhooks)."""
    from .bot import complete_payment

    body = await request.body()
    parsed = payments.parse_xrocket_update(body)
    if not parsed:
        return {"ok": True}  # проверочный запрос xRocket при подключении вебхука — просто отвечаем 200
    payment = await db.payment_by_external("xrocket", parsed[0])
    if not payment or payment["status"] == "paid":
        return {"ok": True}
    paid = parsed[1] == "paid" and payments.xrocket_signature_ok(body, request.headers.get("rocket-pay-signature", ""))
    if not paid:
        # Подпись не сошлась или статус не пришёл — спрашиваем у xRocket напрямую.
        try:
            paid = await payments.xrocket_status(parsed[0]) == "paid"
        except Exception:
            log.warning("xRocket: не удалось проверить счёт %s", parsed[0])
    if paid:
        await complete_payment(payment, note=f"xrocket:{parsed[0]}")
    return {"ok": True}


@app.get("/api/pay/xrocket")
async def xrocket_webhook_ping():
    return {"ok": True}


async def tariff_by_tribute(product: int) -> dict | None:
    tariffs = await access.tariffs()
    found = next((t for t in tariffs if product and int(t.get("tribute_id") or 0) == product), None)
    if found:
        return found
    with_link = [t for t in tariffs if t.get("tribute_link")]
    return with_link[0] if len(with_link) == 1 else None  # один тариф в Tribute — значит он


@app.post("/api/pay/tribute")
async def tribute_webhook(request: Request):
    """Уведомления Tribute: адрес вписывается в Tribute → Settings → API Keys → Webhook."""
    from .bot import complete_payment

    body = await request.body()
    if not payments.tribute_signature_ok(body, request.headers.get("trbt-signature", "")):
        raise HTTPException(401, "bad signature")
    event = payments.parse_tribute(body)
    if not event:
        return {"ok": True}
    uid = event["uid"]
    if event["kind"] in ("product", "subscription"):
        tariff = await tariff_by_tribute(event["product"])
        if not tariff:
            for admin_id in config.ADMIN_IDS:
                await access.send(admin_id, f"Оплата в Tribute от <code>{uid}</code>, но товар {event['product']} не "
                                            "привязан к тарифу. Впиши его ID в Админка → Тарифы и выдай доступ вручную.")
            return {"ok": True}
        if await db.payment_by_external("tribute", event["key"]):
            return {"ok": True}  # Tribute прислал повтор
        await db.upsert_user(uid, event.get("username") or None)
        pending = [p for p in await db.pending_payments("tribute", newer_than=int(time.time()) - 7 * 86400)
                   if p["user_id"] == uid and p["tariff"] == tariff["id"]]
        if pending:
            payment = pending[-1]
        else:
            pid = await db.create_payment(uid, tariff["id"], "tribute", event["amount"] or float(tariff["price"]),
                                          "RUB", int(tariff.get("days") or 0))
            payment = await db.get_payment(pid)
        await db.set_payment_link(payment["id"], event["key"], payment.get("url") or "")
        await complete_payment(payment, note=event["key"], until=event.get("until"))
    elif event["kind"] == "cancelled":
        user = await db.get_user(uid)
        who = f"@{user['username']}" if user and user.get("username") else str(uid)
        for admin_id in config.ADMIN_IDS:
            await access.send(admin_id, f"{who} отменил подписку в Tribute. Доступ останется до конца оплаченного срока.")
    return {"ok": True}


# ---------- Оценка работ из мини-аппа ----------

MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
URL_RE = re.compile(r"^(https?://)?[\w.-]+\.[a-zа-я]{2,}(/\S*)?$", re.I)


@app.get("/api/eval")
async def eval_me(x_init_data: str | None = InitData):
    from modules.evaluation import db as eval_db

    user = await current_user(x_init_data)
    row = await eval_db.upsert_user(user["id"], user.get("username"), user.get("first_name"))
    items = await eval_db.user_reviews(user["id"], 20)
    quota = eval_db.quota(row)
    return {
        "quota": quota,
        "reviews": [{"id": r["id"], "status": r["status"], "url": r.get("url") or "", "total": r.get("total"),
                     "created_at": r.get("created_at"), "ai_status": r.get("ai_status") or "",
                     "ai_score": r.get("ai_score")} for r in items],
        "ai": ai_review.enabled(),
        "max_files": 10,
    }


async def _store_media(uid: int, files: list[tuple[str, str, bytes]], caption: str) -> list[dict]:
    """Отправляет файлы человеку в чат (у него остаётся копия заявки) и берёт их file_id для команды."""
    group = []
    for index, (name, mime, data) in enumerate(files):
        upload = BufferedInputFile(data, filename=name or f"file{index}")
        cap = caption if index == 0 else None
        if mime.startswith("image/") and len(data) <= 10 * 1024 * 1024 and not mime.endswith(("svg+xml", "gif")):
            group.append(InputMediaPhoto(media=upload, caption=cap))
        elif mime.startswith("video/"):
            group.append(InputMediaVideo(media=upload, caption=cap))
        else:
            group.append(InputMediaDocument(media=upload, caption=cap))
    kinds = {type(m) for m in group}
    if InputMediaDocument in kinds and len(kinds) > 1:
        # Документы нельзя смешивать с фото/видео в одном альбоме — отправляем всё документами.
        group = [InputMediaDocument(media=m.media, caption=m.caption) for m in group]
    if len(group) == 1:
        m = group[0]
        send = {InputMediaPhoto: bot.send_photo, InputMediaVideo: bot.send_video,
                InputMediaDocument: bot.send_document}[type(m)]
        messages = [await send(uid, m.media, caption=m.caption)]
    else:
        messages = await bot.send_media_group(uid, group)
    media = []
    for msg in messages:
        if msg.photo:
            p = msg.photo[-1]
            media.append({"type": "photo", "file_id": p.file_id, "size": p.file_size or 0})
        elif msg.video:
            media.append({"type": "video", "file_id": msg.video.file_id, "size": msg.video.file_size or 0,
                          "mime": msg.video.mime_type or "video/mp4"})
        elif msg.document:
            media.append({"type": "document", "file_id": msg.document.file_id,
                          "size": msg.document.file_size or 0, "mime": msg.document.mime_type or ""})
    return media


@app.post("/api/eval/submit")
async def eval_submit(
    files: list[UploadFile] = File(...),
    url: str = Form(""),
    comment: str = Form(""),
    x_init_data: str | None = InitData,
):
    from modules.evaluation import bot as eval_bot
    from modules.evaluation import db as eval_db

    user = await current_user(x_init_data)
    row = await eval_db.upsert_user(user["id"], user.get("username"), user.get("first_name"))
    if row.get("banned"):
        raise HTTPException(403, "Доступ к оценкам закрыт.")
    if eval_db.quota(row)["available"] <= 0:
        raise HTTPException(409, {"code": "limit", "message": "Бесплатные оценки закончились. "
                                  "Резиденты получают оценки с каждой оплатой."})
    if not files or len(files) > 10:
        raise HTTPException(422, "Прикрепи от 1 до 10 скриншотов или видео.")
    url = url.strip()[:300]
    if url and not URL_RE.match(url):
        raise HTTPException(422, "Ссылка выглядит странно. Пример: mysite.ru")
    comment = comment.strip()[:1500]
    loaded, total = [], 0
    for f in files:
        mime = (f.content_type or "").lower()
        if not mime.startswith(("image/", "video/")):
            raise HTTPException(422, "Подходят только картинки и видео.")
        data = await f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise HTTPException(413, f"Файл «{f.filename}» больше 20 МБ. Сожми его или пришли короче видео.")
        total += len(data)
        if total > MAX_TOTAL:
            raise HTTPException(413, "Вместе файлы больше 60 МБ. Убери пару или сожми видео.")
        loaded.append((f.filename or "file", mime, data))
    caption = "Работа на оценку" + (f" · {url}" if url else "")
    try:
        media = await _store_media(user["id"], loaded, caption)
    except TelegramAPIError as exc:
        log.warning("Не удалось отправить файлы %s: %s", user["id"], exc)
        raise HTTPException(409, "Бот не может написать тебе. Нажми /start в чате с ботом и отправь ещё раз.") from exc
    if not media:
        raise HTTPException(502, "Telegram не принял файлы. Попробуй ещё раз.")
    review_id, kind = await eval_db.create_review(user["id"], url, comment, media)
    if review_id is None:
        raise HTTPException(409, "Бесплатные оценки закончились." if kind != "banned" else "Доступ к оценкам закрыт.")
    fresh = await eval_db.get_user(user["id"])
    await eval_bot.say(user["id"], "accepted", eval_bot.kb([eval_bot.btn("Мои оценки", "mine")]),
                       id=review_id, balance=eval_bot.balance_line(fresh) + ".")
    review = await eval_db.get_review(review_id)
    spawn(eval_bot.notify_admins_new(review))
    if ai_review.enabled():
        await eval_db.set_ai(review_id, "pending")
        spawn(run_ai(review_id, user["id"], url, comment, [(m, d) for _, m, d in loaded]))
    return {"ok": True, "id": review_id, "quota": eval_db.quota(fresh), "ai": ai_review.enabled()}


AI_LOCK = asyncio.Semaphore(2)


async def run_ai(review_id: int, uid: int, url: str, comment: str, files: list[tuple[str, bytes]],
                 notify: bool = True) -> dict | None:
    """Нейронка оценивает работу, результат сохраняется и уходит человеку в бота."""
    from modules.evaluation import db as eval_db

    async with AI_LOCK:
        try:
            result = await ai_review.review(url, comment, files)
        except Exception as exc:
            log.warning("AI-оценка #%s не удалась: %s", review_id, exc)
            await eval_db.set_ai(review_id, "error", error=str(exc))
            return None
    await eval_db.set_ai(review_id, "done", result["score"], result)
    if notify:
        markup = access.keyboard([access.app_button("Открыть разбор", "#eval")])
        await access.send(uid, f"<b>Заявка #{review_id}</b>\n\n" + ai_review.format_text(result) +
                          "\n\nЭто автоматическая оценка. Команда тоже посмотрит работу и ответит здесь.", markup)
    return result


async def _review_files(review: dict) -> list[tuple[str, bytes]]:
    """Скачивает из Telegram скриншоты заявки (для повторной проверки)."""
    out = []
    for m in review.get("media") or []:
        mime = "image/jpeg" if m.get("type") == "photo" else m.get("mime") or ""
        if not mime.startswith("image/") or len(out) >= ai_review.MAX_IMAGES:
            continue
        try:
            file = await bot.get_file(m["file_id"])
            buf = await bot.download_file(file.file_path)
            out.append((mime, buf.read()))
        except Exception as exc:
            log.info("Не скачать файл заявки %s: %s", review.get("id"), exc)
    return out


def ai_public(r: dict) -> dict:
    data = r.get("ai_json") or {}
    return {"status": r.get("ai_status") or "", "score": r.get("ai_score"), "verdict": data.get("verdict", ""),
            "good": data.get("good", []), "missing": data.get("missing", []), "errors": data.get("errors", []),
            "advice": data.get("advice", []), "at": r.get("ai_at")}


@app.get("/api/eval/{review_id}")
async def eval_one(review_id: int, x_init_data: str | None = InitData):
    from modules.evaluation import db as eval_db

    user = await current_user(x_init_data)
    r = await eval_db.get_review(review_id)
    if not r or (r["user_id"] != user["id"] and not is_admin(user)):
        raise HTTPException(404, "Заявка не найдена.")
    return {"id": r["id"], "status": r["status"], "url": r.get("url") or "", "comment": r.get("comment") or "",
            "total": r.get("total"), "created_at": r.get("created_at"), "ai": ai_public(r)}


@app.get("/api/admin/works")
async def admin_works(q: str = "", score: int = 0, x_init_data: str | None = InitData):
    from modules.evaluation import db as eval_db

    await admin_user(x_init_data)
    rows = await eval_db.ai_list(q, score if 1 <= score <= 5 else 0)
    return {"enabled": ai_review.enabled(), "model": ai_review.model() if ai_review.enabled() else "",
            "stats": await eval_db.ai_stats(),
            "works": [{"id": r["id"], "user_id": r["user_id"], "username": r.get("username") or "",
                       "name": r.get("first_name") or "", "url": r.get("url") or "", "comment": r.get("comment") or "",
                       "status": r["status"], "total": r.get("total"), "created_at": r["created_at"],
                       "files": len(r.get("media") or []), "ai_error": r.get("ai_error") or "", "ai": ai_public(r)}
                      for r in rows]}


@app.post("/api/admin/works/{review_id}/recheck")
async def admin_work_recheck(review_id: int, x_init_data: str | None = InitData):
    from modules.evaluation import db as eval_db

    await admin_user(x_init_data)
    if not ai_review.enabled():
        raise HTTPException(409, "Нейронка не подключена: добавь ANTHROPIC_API_KEY или OPENROUTER_API_KEY в Railway.")
    r = await eval_db.get_review(review_id)
    if not r:
        raise HTTPException(404, "Заявка не найдена.")
    await eval_db.set_ai(review_id, "pending")
    files = await _review_files(r)
    result = await run_ai(review_id, r["user_id"], r.get("url") or "", r.get("comment") or "", files, notify=False)
    if not result:
        fresh = await eval_db.get_review(review_id)
        raise HTTPException(502, "Нейронка не ответила: " + ((fresh or {}).get("ai_error") or "неизвестная ошибка"))
    return {"ok": True, "ai": ai_public(await eval_db.get_review(review_id))}


# ---------- Админка ----------

@app.post("/api/ping")
async def ping(x_init_data: str | None = InitData):
    tg_user = verify_init_data(x_init_data or "")
    if not tg_user:
        raise HTTPException(401, "Нет входа Telegram.")
    await db.touch(int(tg_user["id"]))
    return {"ok": True}


@app.get("/api/admin/online")
async def admin_online(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    return {"online": await db.online_count()}


@app.get("/api/admin/overview")
async def admin_overview(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    data = await db.overview()
    data["members"] = await access.members_count()
    data["group"] = bool(config.GROUP_ID)
    data["methods"] = payments.methods()
    data["public_url"] = config.PUBLIC_URL
    return data


def user_view(u: dict) -> dict:
    return {
        "id": u["id"], "username": u.get("username") or "", "name": " ".join(
            x for x in (u.get("first_name"), u.get("last_name")) if x) or "",
        "photo": u.get("photo_url") or "", "created_at": u["created_at"], "last_seen": u["last_seen"],
        "started": bool(u.get("started")), "blocked_bot": bool(u.get("blocked_bot")), "banned": bool(u.get("banned")),
        "access": access_info(u), "source": u.get("source") or "",
    }


@app.get("/api/admin/users")
async def admin_users(q: str = "", filter: str = "all", offset: int = 0, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    rows = await db.list_users(q, filter, 50, max(0, offset))
    return {"users": [user_view(u) for u in rows]}


class GrantBody(BaseModel):
    days: int = Field(ge=0, le=3650)   # 0 — навсегда
    tariff: str = Field(default="base", pattern=r"^[a-z0-9_-]{1,32}$")
    notify: bool = True


@app.post("/api/admin/users/{uid}/grant")
async def admin_grant(uid: int, body: GrantBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if not await db.get_user(uid):
        raise HTTPException(404, "Такого человека нет в боте.")
    user = await access.grant(uid, body.tariff, body.days, notify=body.notify, eval_credits=0)
    return {"ok": True, "user": user_view(user)}


@app.post("/api/admin/users/{uid}/revoke")
async def admin_revoke(uid: int, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    await access.revoke(uid, notify=False)
    return {"ok": True, "user": user_view(await db.get_user(uid))}


class BanBody(BaseModel):
    banned: bool


@app.post("/api/admin/users/{uid}/ban")
async def admin_ban(uid: int, body: BanBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if config.is_admin_user(uid):
        raise HTTPException(409, "Админа заблокировать нельзя.")
    await db.update_user(uid, banned=int(body.banned))
    if body.banned:
        await access.revoke(uid)
    return {"ok": True}


@app.get("/api/admin/payments")
async def admin_payments(status: str = "", x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if status and status not in ("pending", "paid", "expired", "cancelled"):
        raise HTTPException(422, "Неизвестный статус.")
    return {"payments": await db.list_payments(status, 200)}


@app.post("/api/admin/payments/{pid}/confirm")
async def admin_confirm(pid: int, x_init_data: str | None = InitData):
    """Оплатили мимо платёжки (переводом) — админ подтверждает, доступ открывается сам."""
    from .bot import complete_payment

    admin = await admin_user(x_init_data)
    payment = await db.get_payment(pid)
    if not payment:
        raise HTTPException(404, "Платёж не найден.")
    if payment["status"] == "paid":
        raise HTTPException(409, "Уже оплачен.")
    await complete_payment(payment, note=f"вручную: {admin['id']}")
    return {"ok": True}


@app.get("/api/admin/tariffs")
async def admin_tariffs(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    return {"tariffs": await access.tariffs()}


class TariffBody(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{2,24}$")
    title: str = Field(min_length=1, max_length=40)
    subtitle: str = Field(default="", max_length=120)
    price: int = Field(ge=0, le=10_000_000)
    price_usd: float = Field(default=0, ge=0, le=1_000_000)
    days: int = Field(ge=0, le=3650)
    stars: int = Field(default=0, ge=0, le=1_000_000)
    active: bool = True
    mentor: bool = False
    badge: str = Field(default="", max_length=20)
    features: list[str] = Field(default_factory=list, max_length=12)
    note: str = Field(default="", max_length=300)
    weekly_seats: int = Field(default=0, ge=0, le=100)
    tribute_link: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")
    tribute_id: int = Field(default=0, ge=0)


@app.put("/api/admin/tariffs")
async def admin_tariffs_save(body: list[TariffBody], x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if not body:
        raise HTTPException(400, "Нужен хотя бы один тариф.")
    if len({t.id for t in body}) != len(body):
        raise HTTPException(400, "У двух тарифов одинаковый ID.")
    if len(body) > 6:
        raise HTTPException(400, "Не больше шести тарифов.")
    data = [t.model_dump() for t in body]
    for t in data:
        t["features"] = [f.strip()[:140] for f in t["features"] if f.strip()]
    await db.set_setting("tariffs", data)
    return {"tariffs": await access.tariffs()}


class CompareRow(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    cells: dict[str, str] = Field(default_factory=dict)
    default: str = Field(default="+", max_length=40)


@app.get("/api/admin/compare")
async def admin_compare(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    return {"rows": await access.compare_rows(), "tariffs": [{"id": t["id"], "title": t["title"]} for t in await access.tariffs()]}


@app.put("/api/admin/compare")
async def admin_compare_save(body: list[CompareRow], x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if len(body) > 12:
        raise HTTPException(400, "Не больше 12 строк.")
    rows = [{"label": r.label.strip(), "cells": {k[:24]: v.strip()[:40] for k, v in r.cells.items()}, "default": r.default.strip()}
            for r in body if r.label.strip()]
    await db.set_setting("compare", rows)
    return {"rows": await access.compare_rows()}


@app.get("/api/admin/content")
async def admin_content(kind: str = "", x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    items = await db.list_content(kind or None, published_only=False)
    return {"items": [dict(i, media=content.media(i)) for i in items]}


class ContentBody(BaseModel):
    kind: str = Field(pattern=r"^(lesson|material|prompt|resource|agent|skill|plugin|cskill|cplugin|guide|free|marathon|post|review)$")
    module: str = Field(default="", max_length=60)
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=60000)
    icon: str = Field(default="", max_length=40)
    free: bool = False
    position: int = Field(default=0, ge=0, le=100000)
    published: bool = True
    minutes: int = Field(default=0, ge=0, le=600)
    media: list[str] = Field(default_factory=list, max_length=6)


@app.post("/api/admin/content")
async def admin_content_create(body: ContentBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    data = body.model_dump()
    data["free"], data["published"] = int(data["free"]), int(data["published"])
    data["media"] = [m for m in data["media"] if re.match(r"^(https://|/uploads/|img/)[\w./%-]+$", m)]
    cid = await db.save_content(data)
    return {"item": await db.get_content(cid)}


@app.put("/api/admin/content/{cid}")
async def admin_content_update(cid: int, body: ContentBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if not await db.get_content(cid):
        raise HTTPException(404, "Материал не найден.")
    data = body.model_dump()
    data["free"], data["published"] = int(data["free"]), int(data["published"])
    data["media"] = [m for m in data["media"] if re.match(r"^(https://|/uploads/|img/)[\w./%-]+$", m)]
    await db.save_content(data, cid)
    return {"item": await db.get_content(cid)}


UPLOAD_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@app.post("/api/admin/upload")
async def admin_upload(file: UploadFile = File(...), x_init_data: str | None = InitData):
    """Картинка для подборки (скриншот сайта). Хранится на диске сервера рядом с базами."""
    await admin_user(x_init_data)
    ext = UPLOAD_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(422, "Подходят JPG, PNG или WebP.")
    data = await file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Картинка больше 8 МБ.")
    name = f"{uuid.uuid4().hex}.{ext}"
    (config.DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "uploads" / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}


@app.delete("/api/admin/content/{cid}")
async def admin_content_delete(cid: int, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    await db.delete_content(cid)
    return {"ok": True}


async def broadcast(admin_id: int, ids: list[int], body: str, image: bytes | None, button: str = "",
                    path: str = "") -> None:
    sent = 0
    photo_id = None
    markup = access.keyboard([access.app_button(button, path)]) if button else None
    fits = image is not None and texts.plain_len(body) <= 1024
    for index, uid in enumerate(ids):
        try:
            if image is not None:
                msg = await bot.send_photo(uid, photo_id or BufferedInputFile(image, filename="post.jpg"),
                                           caption=body if fits and body else None,
                                           reply_markup=markup if fits or not body else None)
                if msg.photo:
                    photo_id = msg.photo[-1].file_id
                if body and not fits:
                    await bot.send_message(uid, body, reply_markup=markup)
            else:
                await bot.send_message(uid, body, reply_markup=markup, disable_web_page_preview=True)
            sent += 1
        except TelegramAPIError as exc:
            if "blocked" in str(exc).lower() or "deactivated" in str(exc).lower():
                await db.update_user(uid, blocked_bot=1)
        if index % 25 == 24:
            await asyncio.sleep(1.1)
    await access.send(admin_id, f"<b>Рассылка завершена</b>: доставлено {sent} из {len(ids)}.")


@app.post("/api/admin/content/{cid}/notify")
async def admin_content_notify(cid: int, x_init_data: str | None = InitData):
    admin = await admin_user(x_init_data)
    item = await db.get_content(cid)
    if not item or not item["published"]:
        raise HTTPException(404, "Опубликуй материал, потом рассылай.")
    ids = await db.audience("notify")
    body = await access.text("new_post", title=texts.telegram_html(item["title"]),
                             kind=content.KINDS.get(item["kind"], "материал"))
    spawn(broadcast(admin["id"], ids, body, None, "Открыть", f"#item/{cid}"))
    return {"ok": True, "message": f"Отправляю {len(ids)} людям с включёнными уведомлениями."}


class BroadcastBody(BaseModel):
    text: str = Field(default="", max_length=4096)
    image: str = Field(default="", max_length=12_000_000)
    audience: str = Field(default="all", pattern=r"^(all|residents|guests|notify)$")
    button: bool = True


def decode_image(data: str) -> bytes | None:
    if not data:
        return None
    raw = data.split(",", 1)[1] if data.startswith("data:") else data
    try:
        image = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "Картинка не читается.") from exc
    if len(image) > 9 * 1024 * 1024:
        raise HTTPException(413, "Картинка больше 9 МБ.")
    return image


@app.post("/api/admin/broadcast")
async def admin_broadcast(body: BroadcastBody, x_init_data: str | None = InitData):
    admin = await admin_user(x_init_data)
    message = texts.telegram_html(body.text)
    image = decode_image(body.image)
    if not message and not image:
        raise HTTPException(422, "Добавь текст или картинку.")
    ids = await db.audience(body.audience)
    spawn(broadcast(admin["id"], ids, message, image, "Открыть C&C" if body.button else ""))
    return {"ok": True, "message": f"Рассылка запущена: {len(ids)} человек. Итог придёт в чат с ботом."}


@app.get("/api/admin/texts")
async def admin_texts(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    custom = await db.get_setting("texts", {}) or {}
    return {"texts": [{"key": k, "title": v["title"], "hint": v["hint"], "default": v["text"],
                       "text": custom.get(k) or v["text"], "changed": bool(custom.get(k))}
                      for k, v in texts.TEXTS.items()]}


class TextBody(BaseModel):
    text: str = Field(default="", max_length=4000)


@app.put("/api/admin/texts/{key}")
async def admin_text_save(key: str, body: TextBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    if key not in texts.TEXTS:
        raise HTTPException(404, "Нет такого текста.")
    custom = dict(await db.get_setting("texts", {}) or {})
    value = texts.telegram_html(body.text)
    if value and value != texts.TEXTS[key]["text"]:
        custom[key] = value
    else:
        custom.pop(key, None)
    await db.set_setting("texts", custom)
    return {"ok": True, "text": custom.get(key) or texts.TEXTS[key]["text"]}


@app.post("/api/admin/texts/{key}/test")
async def admin_text_test(key: str, x_init_data: str | None = InitData):
    admin = await admin_user(x_init_data)
    if key not in texts.TEXTS:
        raise HTTPException(404, "Нет такого текста.")
    sample = {"until": "Доступ до 1 декабря.", "date": "1 декабря", "title": "Как найти первого клиента",
              "kind": "урок", "day": 2}
    image = {"welcome": "welcome", "abandoned": "help", "paid": "paid"}.get(key)
    ok = await access.send(admin["id"], await access.text(key, **sample), image=image)
    return {"ok": ok}


class SettingsBody(BaseModel):
    members_manual: int = Field(default=0, ge=0, le=10_000_000)
    card_link: str | None = Field(default=None, max_length=300)


async def card_link() -> str:
    value = await db.get_setting("card_link", None)
    return (config.CARD_PAY_LINK if value is None else str(value)).strip()


@app.post("/api/admin/xrocket/check")
async def admin_xrocket_check(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    hook = f"{config.PUBLIC_URL.rstrip('/')}/api/pay/xrocket" if config.PUBLIC_URL else ""
    if not config.XROCKET_PAY_TOKEN:
        return {"ok": False, "message": "В Railway нет переменной XROCKET_PAY_TOKEN. Добавь её и сделай Redeploy.",
                "webhook": hook}
    try:
        info = await payments.xrocket_info()
    except Exception as exc:
        return {"ok": False, "message": str(exc), "webhook": hook}
    name = info.get("name") or info.get("appName") or "касса"
    return {"ok": True, "message": f"xRocket подключён: {name}. Кнопка появится у тарифов, где указана цена в $.",
            "webhook": hook}


@app.get("/api/admin/settings")
async def admin_settings(x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    return {"members_manual": int(await db.get_setting("members_manual", 0) or 0), "card_link": await card_link(),
            "xrocket": bool(config.XROCKET_PAY_TOKEN),
            "group_id": config.GROUP_ID, "support": config.SUPPORT_USERNAME, "personal": config.PERSONAL_USERNAME,
            "methods": payments.methods(), "public_url": config.PUBLIC_URL, "bot": config.BOT_USERNAME}


@app.put("/api/admin/settings")
async def admin_settings_save(body: SettingsBody, x_init_data: str | None = InitData):
    await admin_user(x_init_data)
    await db.set_setting("members_manual", body.members_manual)
    if body.card_link is not None:
        link = body.card_link.strip()
        if link and not re.match(r"^https://\S+$", link):
            raise HTTPException(422, "Ссылка для оплаты картой должна начинаться с https://")
        await db.set_setting("card_link", link)
    access._members_cache["at"] = 0
    return {"ok": True}


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ---------- Модули и статика ----------

def mount_modules() -> None:
    from modules.evaluation import api as eval_api
    from modules.parser import api as parser_api

    app.mount("/parser", parser_api.app)
    app.mount("/eval", eval_api.app)
    (config.DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=config.DATA_DIR / "uploads"), name="uploads")
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


mount_modules()

