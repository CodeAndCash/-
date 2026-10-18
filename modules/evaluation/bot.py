"""Telegram-бот Evaluation C&C: приём скриншотов/видео, оплата, уведомления админам и ответы."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument,
    InputMediaPhoto, InputMediaVideo, LabeledPrice, Message, PreCheckoutQuery, WebAppInfo,
)

from . import card
from . import config
from . import db
from . import render
from . import texts

log = logging.getLogger("evaluation.bot")
from cc.tg import bot  # один общий бот C&C Family
dp = Router(name="evaluation")

URL_RE = re.compile(r"(https?://\S+|(?:[\w-]+\.)+[a-zа-я]{2,}(?:/\S*)?)", re.I)
DRAFT_TTL = 6 * 60 * 60
DRAFTS: dict[int, dict] = {}       # черновик заявки: файлы, ссылка, комментарий
DRAFT_TASKS: dict[int, asyncio.Task] = {}
REPLY_TO: dict[int, int] = {}      # человек отвечает по заявке
ADMIN_REPLY: dict[int, int] = {}   # админ пишет человеку прямо из чата


def esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


def is_admin(user) -> bool:
    return bool(user) and config.is_admin_user(user.id, user.username)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def eval_btn(text: str = "Отправить работу") -> InlineKeyboardButton:
    """Раздел «Оценка работ» в общем мини-аппе C&C Family."""
    from cc import config as _cc
    if _cc.PUBLIC_URL:
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=_cc.app_url("#eval")))
    return InlineKeyboardButton(text=text, callback_data="how")


def app_btn(text: str, review_id: int | None = None) -> InlineKeyboardButton | None:
    if not config.WEBAPP_URL:
        return None
    url = config.WEBAPP_URL + f"/?v={config.APP_VERSION}" + (f"&r={review_id}" if review_id else "")
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


async def say(chat_id: int, key: str, markup: InlineKeyboardMarkup | None = None, **values) -> bool:
    """Отправляет текст из «Сообщений» (с картинкой, если админ её добавил)."""
    raw, image, _changed = await db.get_text(key)
    text = texts.fill(raw, values)
    try:
        if image:
            photo = BufferedInputFile(image, filename=f"{key}.jpg")
            if texts.plain_len(text) <= 1024:
                await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
                return True
            await bot.send_photo(chat_id, photo)
        await bot.send_message(chat_id, text, reply_markup=markup)
        return True
    except TelegramAPIError:
        log.warning("Could not send %s to %s", key, chat_id)
        return False


def rub_word(n: int) -> str:
    a, b = n % 10, n % 100
    return "оценка" if a == 1 and b != 11 else ("оценки" if 2 <= a <= 4 and not 12 <= b <= 14 else "оценок")


def balance_line(user: dict) -> str:
    q = db.quota(user)
    parts = []
    if q["free_left"]:
        parts.append(f"бесплатных — <b>{q['free_left']}</b>")
    if q["credits"]:
        parts.append(("оплаченных" if config.PAID_ENABLED else "дополнительных") + f" — <b>{q['credits']}</b>")
    return ("Доступно: " + ", ".join(parts)) if parts else "Бесплатные оценки закончились"


def main_menu(user) -> InlineKeyboardMarkup:
    rows = [[eval_btn()], [btn("Мои оценки", "mine")]]
    if is_admin(user):
        admin = app_btn("Открыть админку оценок")
        if admin:
            rows.insert(0, [admin])
    return kb(*rows)


async def ensure_user(tg_user) -> dict:
    return await db.upsert_user(tg_user.id, tg_user.username, tg_user.first_name)


# ---------- Старт и меню ----------

@dp.message(Command("cancel"))
async def cancel(message: Message) -> None:
    uid = message.from_user.id
    DRAFTS.pop(uid, None)
    REPLY_TO.pop(uid, None)
    ADMIN_REPLY.pop(uid, None)
    await message.answer("Отменено.", reply_markup=main_menu(message.from_user))


@dp.callback_query(F.data == "how")
async def how(call: CallbackQuery) -> None:
    await call.answer()
    await say(call.from_user.id, "how", kb([eval_btn()]))


@dp.callback_query(F.data == "mine")
async def mine(call: CallbackQuery) -> None:
    await call.answer()
    user = await ensure_user(call.from_user)
    items = await db.user_reviews(call.from_user.id, 10)
    status = {"new": "в очереди", "work": "смотрим", "done": "готово", "rejected": "отклонено"}
    if not items:
        text = "У тебя пока нет заявок. Пришли скриншоты или видео сайта — и начнём."
    else:
        lines = ["<b>Мои оценки</b>", ""]
        for r in items:
            score = f" · <b>{render.fmt_score(r['total'])}/10</b>" if r.get("total") is not None and r["status"] == "done" else ""
            site = f" · {esc(r['url'][:40])}" if r.get("url") else ""
            lines.append(f"#{r['id']} — {status.get(r['status'], r['status'])}{score}{site}")
        text = "\n".join(lines)
    await call.message.answer(text + f"\n\n{balance_line(user)}.",
                              reply_markup=kb([btn("Купить оценку", "buy")]) if config.PAID_ENABLED else None)


# ---------- Оплата ----------

def pay_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.PRICE_STARS:
        rows.append([btn(f"Оплатить звёздами · {config.PRICE_STARS} ⭐", "stars")])
    rows.append([btn(f"Перевод {config.PRICE_RUB} ₽ — написать @{config.PAY_CONTACT}", "transfer")])
    return kb(*rows)


async def send_pay_offer(chat_id: int) -> None:
    if not config.PAID_ENABLED:
        await say(chat_id, "limit", free=config.FREE_REVIEWS)
        return
    await say(chat_id, "pay_offer", pay_keyboard(), price=config.PRICE_RUB, stars=config.PRICE_STARS)


@dp.callback_query(F.data == "buy")
async def buy(call: CallbackQuery) -> None:
    await call.answer()
    if not config.PAID_ENABLED:
        await say(call.from_user.id, "limit", free=config.FREE_REVIEWS)
        return
    await call.message.answer(
        f"<b>Купить оценку</b>\n\nОдна оценка сайта — <b>{config.PRICE_RUB} ₽</b>.\n"
        + (f"Звёздами Telegram — {config.PRICE_STARS} ⭐, зачисляется сразу.\n" if config.PRICE_STARS else "")
        + f"Переводом — напиши @{esc(config.PAY_CONTACT)}, оценку добавят вручную.",
        reply_markup=pay_keyboard(),
    )


@dp.callback_query(F.data == "transfer")
async def transfer(call: CallbackQuery) -> None:
    await call.answer()
    if not config.PAID_ENABLED:
        return
    await say(call.from_user.id, "transfer", contact="@" + esc(config.PAY_CONTACT), id=call.from_user.id,
              price=config.PRICE_RUB)


@dp.callback_query(F.data == "stars")
async def stars(call: CallbackQuery) -> None:
    await call.answer()
    if not (config.PAID_ENABLED and config.PRICE_STARS):
        return
    await bot.send_invoice(
        call.from_user.id,
        title=f"Оценка сайта · {config.BRAND}",
        description="Одна оценка сайта по скриншотам или видео: 5 критериев и советы, что улучшить.",
        payload=f"review:{call.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label="Оценка сайта", amount=config.PRICE_STARS)],
        provider_token="",
    )


@dp.pre_checkout_query(F.invoice_payload.startswith("review:"))
async def pre_checkout(query: PreCheckoutQuery) -> None:
    ok = query.invoice_payload == f"review:{query.from_user.id}" and query.currency == "XTR"
    await query.answer(ok=ok, error_message=None if ok else "Платёж не прошёл проверку, попробуй ещё раз.")


@dp.message(F.successful_payment, F.successful_payment.invoice_payload.startswith("review:"))
async def paid(message: Message) -> None:
    payment = message.successful_payment
    await ensure_user(message.from_user)
    added = await db.record_star_payment(message.from_user.id, payment.total_amount, payment.telegram_payment_charge_id)
    user = await db.get_user(message.from_user.id)
    if added:
        await say(message.chat.id, "paid", draft_keyboard() if message.from_user.id in DRAFTS else None,
                  balance=balance_line(user) + ".")
    for admin_id in await db.admin_chat_ids():
        await safe_send(admin_id, f"Оплата звёздами: {esc(render.user_name(user))} · {payment.total_amount} ⭐")


# ---------- Черновик заявки ----------

def draft_keyboard() -> InlineKeyboardMarkup:
    return kb([btn("Отправить на оценку", "submit")], [btn("Очистить", "clear")])


def media_of(message: Message) -> dict | None:
    if message.photo:
        p = message.photo[-1]
        return {"type": "photo", "file_id": p.file_id, "size": p.file_size or 0}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id, "size": message.video.file_size or 0,
                "mime": message.video.mime_type or "video/mp4"}
    if message.animation:
        return {"type": "video", "file_id": message.animation.file_id, "size": message.animation.file_size or 0,
                "mime": message.animation.mime_type or "video/mp4"}
    if message.document and (message.document.mime_type or "").startswith(("image/", "video/")):
        return {"type": "document", "file_id": message.document.file_id, "size": message.document.file_size or 0,
                "mime": message.document.mime_type}
    return None


def draft_text(draft: dict, user: dict) -> str:
    n = len(draft["media"])
    lines = ["<b>Черновик заявки</b>", "", f"Файлов: <b>{n}</b> из {config.MAX_MEDIA}"]
    lines.append(f"Ссылка: {esc(draft['url'])}" if draft["url"] else "Ссылка: не добавлена")
    if draft["comment"]:
        lines.append(f"Что важно: {esc(draft['comment'][:200])}")
    lines.append("")
    if not n:
        lines.append("Пришли хотя бы один скриншот или видео сайта.")
    else:
        lines.append("Можно добавить ещё файлы, ссылку или комментарий — или отправлять.")
    q = db.quota(user)
    if q["available"] <= 0:
        lines += ["", f"Бесплатные оценки закончились — одна оценка {config.PRICE_RUB} ₽." if config.PAID_ENABLED
                  else "Бесплатные оценки закончились — эту заявку отправить не получится."]
    return "\n".join(lines)


def new_draft() -> dict:
    return {"media": [], "url": "", "comment": "", "msg": None, "ts": time.time()}


def get_draft(uid: int) -> dict:
    draft = DRAFTS.get(uid)
    if not draft or time.time() - draft["ts"] > DRAFT_TTL:
        draft = DRAFTS[uid] = new_draft()
    draft["ts"] = time.time()
    return draft


async def show_draft(uid: int, chat_id: int, delay: float = 1.2) -> None:
    """Альбом приходит несколькими сообщениями — карточку черновика показываем один раз, после паузы."""
    old = DRAFT_TASKS.pop(uid, None)
    if old and not old.done():
        old.cancel()

    async def run():
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        draft = DRAFTS.get(uid)
        if not draft:
            return
        user = await db.get_user(uid) or {}
        text = draft_text(draft, user)
        markup = draft_keyboard() if draft["media"] else kb([btn("Очистить", "clear")])
        if draft.get("msg"):
            try:
                await bot.delete_message(chat_id, draft["msg"])
            except TelegramAPIError:
                pass
        sent = await bot.send_message(chat_id, text, reply_markup=markup)
        draft["msg"] = sent.message_id

    DRAFT_TASKS[uid] = asyncio.create_task(run())


async def got_media(message: Message) -> None:
    user = await ensure_user(message.from_user)
    if user.get("banned"):
        return
    media = media_of(message)
    if not media:
        await message.answer("Пришли картинку или видео — другие файлы бот не принимает.")
        return
    draft = get_draft(message.from_user.id)
    if len(draft["media"]) >= config.MAX_MEDIA:
        await message.answer(f"В одной заявке до {config.MAX_MEDIA} файлов — остальные не добавлены.")
        return
    draft["media"].append(media)
    if message.caption:
        apply_text(draft, message.caption)
    await show_draft(message.from_user.id, message.chat.id)


def apply_text(draft: dict, text: str) -> None:
    text = text.strip()
    match = URL_RE.search(text)
    if match and not draft["url"]:
        draft["url"] = match.group(1).rstrip(".,)")[:300]
        text = (text[: match.start()] + text[match.end():]).strip(" \n,-—")
    if text:
        draft["comment"] = (draft["comment"] + "\n" + text).strip()[:1500]


@dp.callback_query(F.data == "clear")
async def clear(call: CallbackQuery) -> None:
    await call.answer("Черновик очищен")
    DRAFTS.pop(call.from_user.id, None)
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass


@dp.callback_query(F.data == "submit")
async def submit(call: CallbackQuery) -> None:
    uid = call.from_user.id
    draft = DRAFTS.get(uid)
    if not draft or not draft["media"]:
        await call.answer("Сначала пришли скриншоты или видео", show_alert=True)
        return
    await ensure_user(call.from_user)
    review_id, kind = await db.create_review(uid, draft["url"], draft["comment"], draft["media"])
    if review_id is None:
        await call.answer()
        if kind == "banned":
            await call.message.answer("Доступ к боту закрыт.")
        else:
            await send_pay_offer(uid)
        return
    await call.answer("Отправлено!")
    DRAFTS.pop(uid, None)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass
    user = await db.get_user(uid)
    await say(uid, "accepted", kb([btn("Мои оценки", "mine")]), id=review_id, balance=balance_line(user) + ".")
    review = await db.get_review(review_id)
    await notify_admins_new(review)
    await start_ai(review)


async def start_ai(review: dict) -> None:
    """Заявку из чата тоже сразу смотрит нейронка (если подключена)."""
    from cc import ai_review
    from cc.api import _review_files, run_ai, spawn

    if not ai_review.enabled():
        return
    await db.set_ai(review["id"], "pending")

    async def go():
        files = await _review_files(review)
        await run_ai(review["id"], review["user_id"], review.get("url") or "", review.get("comment") or "", files)

    spawn(go())


# ---------- Уведомления админам ----------

def admin_card(review: dict) -> str:
    who = render.user_name({"username": review.get("username"), "first_name": review.get("first_name"), "id": review["user_id"]})
    kind = "бесплатная" if review["kind"] == "free" else ("платная" if config.PAID_ENABLED else "дополнительная")
    lines = [f"<b>Новая заявка #{review['id']}</b> · {kind}", f"От: {esc(who)} (<code>{review['user_id']}</code>)",
             f"Файлов: {len(review.get('media') or [])}"]
    if review.get("url"):
        lines.append(f"Сайт: {esc(review['url'])}")
    if review.get("comment"):
        lines.append(f"<blockquote>{esc(review['comment'][:700])}</blockquote>")
    return "\n".join(lines)


def admin_keyboard(review_id: int, taken: bool = False) -> InlineKeyboardMarkup:
    rows = []
    app = app_btn("Оценить в мини-аппе", review_id)
    if app:
        rows.append([app])
    if not taken:
        rows.append([btn("Взять в работу", f"take:{review_id}")])
    rows.append([btn("Написать человеку", f"areply:{review_id}")])
    return kb(*rows)


async def send_media(chat_id: int, media: list[dict]) -> None:
    """Отправляет файлы заявки альбомами: фото и видео вместе, документы отдельно."""
    visual = [m for m in media if m["type"] in ("photo", "video")]
    docs = [m for m in media if m["type"] == "document"]
    for group, make in ((visual, lambda m: InputMediaPhoto(media=m["file_id"]) if m["type"] == "photo" else InputMediaVideo(media=m["file_id"])),
                        (docs, lambda m: InputMediaDocument(media=m["file_id"]))):
        if not group:
            continue
        try:
            if len(group) == 1:
                m = group[0]
                send = {"photo": bot.send_photo, "video": bot.send_video, "document": bot.send_document}[m["type"]]
                await send(chat_id, m["file_id"])
            else:
                await bot.send_media_group(chat_id, [make(m) for m in group[:10]])
        except TelegramAPIError:
            log.exception("Could not send media to %s", chat_id)


async def notify_admins_new(review: dict) -> None:
    for admin_id in await db.admin_chat_ids():
        try:
            await send_media(admin_id, review.get("media") or [])
            await bot.send_message(admin_id, admin_card(review), reply_markup=admin_keyboard(review["id"]))
        except TelegramAPIError:
            log.warning("Could not notify admin %s", admin_id)


async def safe_send(chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramAPIError:
        log.warning("Could not message %s", chat_id)
        return False


async def notify_other_admins(except_id: int, text: str, review_id: int | None = None) -> None:
    for admin_id in await db.admin_chat_ids():
        if admin_id != except_id:
            markup = kb([app_btn("Открыть", review_id)]) if review_id and config.WEBAPP_URL else None
            await safe_send(admin_id, text, reply_markup=markup)


@dp.callback_query(F.data.startswith("take:"))
async def take(call: CallbackQuery) -> None:
    if not is_admin(call.from_user):
        await call.answer("Только для админов", show_alert=True)
        return
    review_id = int(call.data.split(":")[1])
    name = render.user_name({"username": call.from_user.username, "first_name": call.from_user.first_name, "id": call.from_user.id})
    review = await db.take_review(review_id, call.from_user.id, name)
    if not review:
        await call.answer("Заявку уже взяли или она закрыта", show_alert=True)
        return
    await call.answer("Заявка твоя")
    try:
        await call.message.edit_reply_markup(reply_markup=admin_keyboard(review_id, taken=True))
    except TelegramAPIError:
        pass
    await notify_taken(review, name, call.from_user.id)


async def notify_taken(review: dict, admin_name: str, admin_id: int) -> None:
    await say(review["user_id"], "taken", id=review["id"], admin=esc(admin_name))
    await notify_other_admins(admin_id, f"Заявку #{review['id']} взял {esc(admin_name)}.", review["id"])


# ---------- Переписка ----------

@dp.callback_query(F.data.startswith("reply:"))
async def user_reply(call: CallbackQuery) -> None:
    review_id = int(call.data.split(":")[1])
    review = await db.get_review(review_id)
    if not review or review["user_id"] != call.from_user.id:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    REPLY_TO[call.from_user.id] = review_id
    await call.answer()
    await call.message.answer(f"Напиши сообщение по заявке #{review_id} — я передам его команде. /cancel — отменить.")


@dp.callback_query(F.data.startswith("areply:"))
async def admin_reply(call: CallbackQuery) -> None:
    if not is_admin(call.from_user):
        await call.answer("Только для админов", show_alert=True)
        return
    review_id = int(call.data.split(":")[1])
    ADMIN_REPLY[call.from_user.id] = review_id
    await call.answer()
    await call.message.answer(f"Напиши сообщение для автора заявки #{review_id}. /cancel — отменить.")


async def send_admin_message(review: dict, text: str, admin_name: str) -> bool:
    return await safe_send(
        review["user_id"], render.admin_message(review["id"], text, admin_name),
        reply_markup=kb([btn("Ответить", f"reply:{review['id']}")]),
    )


def _in_dialog(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return uid in REPLY_TO or uid in ADMIN_REPLY


@dp.message(F.text, _in_dialog)
async def text_message(message: Message) -> None:
    uid = message.from_user.id
    text = (message.text or "").strip()
    if text.startswith("/"):
        REPLY_TO.pop(uid, None)
        ADMIN_REPLY.pop(uid, None)
        await message.answer("Отменено.")
        return
    user = await ensure_user(message.from_user)
    if user.get("banned"):
        return

    if uid in ADMIN_REPLY and is_admin(message.from_user):
        review_id = ADMIN_REPLY.pop(uid)
        review = await db.get_review(review_id)
        if review:
            name = render.user_name(user)
            await db.add_message(review_id, uid, True, text)
            ok = await send_admin_message(review, text, name)
            await message.answer("Отправлено." if ok else "Не получилось доставить: человек остановил бота.")
            await notify_other_admins(uid, f"{esc(name)} написал автору #{review_id}:\n<blockquote>{esc(text[:500])}</blockquote>", review_id)
        return

    if uid in REPLY_TO:
        review_id = REPLY_TO.pop(uid)
        await db.add_message(review_id, uid, False, text)
        await message.answer("Передал команде. Ответ придёт сюда.")
        who = render.user_name(user)
        rows = [[btn("Ответить", f"areply:{review_id}")]]
        if config.WEBAPP_URL:
            rows.insert(0, [app_btn("Открыть заявку", review_id)])
        for admin_id in await db.admin_chat_ids():
            await safe_send(admin_id, f"<b>Сообщение по заявке #{review_id}</b> от {esc(who)}\n<blockquote>{esc(text[:1500])}</blockquote>",
                            reply_markup=kb(*rows))
        return



# ---------- Результат, отклонение, файлы — вызывает мини-апп ----------

async def send_result(review: dict) -> bool:
    try:
        if review.get("total") is None or not review.get("scores"):
            raise LookupError  # без баллов — только текст, без картинки
        image = card.render_card(review, config.BRAND)
        await bot.send_photo(review["user_id"], BufferedInputFile(image, filename=f"ocenka-{review['id']}.png"),
                             caption=f"<b>{esc(config.BRAND)}</b> · заявка #{review['id']}")
    except LookupError:
        pass
    except TelegramAPIError:
        log.warning("Could not send card to %s", review["user_id"])
    except Exception:
        log.exception("Card render failed")
    outro, _image, _changed = await db.get_text("result_outro")
    return await safe_send(review["user_id"], render.review_result(review, texts.fill(outro, {})),
                           reply_markup=kb([btn("Ответить", f"reply:{review['id']}")], [eval_btn("Оценить ещё работу")]))


async def send_rejected(review: dict, reason: str) -> bool:
    return await say(review["user_id"], "rejected", kb([eval_btn("Отправить заново")]), id=review["id"],
                     reason=f"<blockquote>{esc(reason)}</blockquote>" if reason else "")


async def notify_credits(user_id: int, amount: int, credits: int) -> bool:
    return await safe_send(
        user_id,
        f"<b>{'Оплата зачислена' if config.PAID_ENABLED else 'Тебе добавили оценку'}</b>: +{amount} {rub_word(amount)}.\nНа балансе: <b>{credits}</b>. Присылай скриншоты или видео сайта.",
    )


async def download_media(file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    data = await bot.download_file(file.file_path)
    return data.read()


async def broadcast(text: str, images: list[bytes], user_ids: list[int]) -> tuple[int, int]:
    """Рассылка: до 30 сообщений в секунду (лимит Telegram), ошибки отдельных людей не останавливают её."""
    sent = 0
    for index, uid in enumerate(user_ids):
        try:
            if images:
                files = [BufferedInputFile(img, filename=f"{i}.jpg") for i, img in enumerate(images)]
                short = texts.plain_len(text) <= 1024
                if len(files) == 1:
                    await bot.send_photo(uid, files[0], caption=text if short and text else None)
                else:
                    group = [InputMediaPhoto(media=f) for f in files]
                    if short and text:
                        group[0] = InputMediaPhoto(media=files[0], caption=text)
                    await bot.send_media_group(uid, group)
                if text and not short:
                    await bot.send_message(uid, text)
            else:
                await bot.send_message(uid, text)
            sent += 1
        except TelegramAPIError:
            pass
        if index % 25 == 24:
            await asyncio.sleep(1)
    return sent, len(user_ids)
