"""Доступ резидентов: выдача после оплаты, закрытая группа, парсер/скрипты/оценки, окончание и напоминания."""
from __future__ import annotations

import asyncio
import html
import datetime as dt
import logging
import re
import time
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from . import config, db, texts
from .tg import bot

log = logging.getLogger("cc.access")
ASSETS = Path(__file__).with_name("assets")
MSK = dt.timezone(dt.timedelta(hours=3))
_photo_ids: dict[str, str] = {}
_members_cache: dict[str, float] = {"value": 0, "at": 0}


# ---------- Сообщения ----------

def app_button(text: str = "Открыть C&C", path: str = "") -> InlineKeyboardButton | None:
    if not config.PUBLIC_URL:
        return None
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=config.app_url(path)))


def url_button(text: str, username: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=f"https://t.me/{username}")


def keyboard(*rows) -> InlineKeyboardMarkup | None:
    clean = [[b for b in row if b] for row in rows]
    clean = [row for row in clean if row]
    return InlineKeyboardMarkup(inline_keyboard=clean) if clean else None


async def text(key: str, **values) -> str:
    custom = (await db.get_setting("texts", {}) or {}).get(key)
    raw = custom if custom else texts.TEXTS[key]["text"]
    return texts.fill(raw, **values)


def asset(name: str | None) -> Path | None:
    """Картинка или анимация из cc/assets: «welcome» → welcome.mp4, если есть, иначе welcome.jpg."""
    if not name:
        return None
    candidates = [name] if "." in name else [name + ".mp4", name + ".jpg"]
    return next((ASSETS / c for c in candidates if (ASSETS / c).exists()), None)


async def send(uid: int, body: str, markup=None, image: str | None = None) -> bool:
    """Отправка с картинкой или анимацией из cc/assets. Отмечает тех, кто остановил бота."""
    try:
        path = asset(image)
        if path and texts.plain_len(body) <= 1024:
            animated = path.suffix == ".mp4"
            key = path.name
            cached = _photo_ids.get(key)

            async def push(media):
                if animated:
                    return await bot.send_animation(uid, media, caption=body, reply_markup=markup,
                                                    width=1280, height=640)
                return await bot.send_photo(uid, media, caption=body, reply_markup=markup)
            try:
                msg = await push(cached or FSInputFile(path))
            except TelegramAPIError as exc:
                if not cached or "forbidden" in str(exc).lower() or "chat not found" in str(exc).lower():
                    raise
                _photo_ids.pop(key, None)
                msg = await push(FSInputFile(path))
            anim, photo = getattr(msg, "animation", None), getattr(msg, "photo", None)
            if animated and anim:
                _photo_ids[key] = anim.file_id
            elif photo:
                _photo_ids[key] = photo[-1].file_id
        else:
            await bot.send_message(uid, body, reply_markup=markup, disable_web_page_preview=True)
        return True
    except TelegramAPIError as exc:
        low = str(exc).lower()
        if "blocked" in low or "deactivated" in low or "forbidden" in low:
            await db.update_user(uid, blocked_bot=1)
        log.info("Не удалось написать %s: %s", uid, exc)
        return False


def fmt_date(ts: int) -> str:
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
    d = dt.datetime.fromtimestamp(ts, MSK)
    return f"{d.day} {months[d.month - 1]}"


# ---------- Тарифы ----------

TARIFF_DEFAULTS = {"subtitle": "", "price": 0, "price_usd": 0, "days": 0, "stars": 0, "active": False, "mentor": False,
                   "weekly_seats": 0, "badge": "", "features": [], "note": "", "tribute_link": "", "tribute_id": 0}


async def tariffs() -> list[dict]:
    """Тарифы из админки (в том порядке, как там стоят). Пока ничего не сохраняли — стандартные два."""
    saved = await db.get_setting("tariffs")
    known = {t["id"]: t for t in texts.DEFAULT_TARIFFS}
    if not isinstance(saved, list) or not saved:
        return [dict(t) for t in texts.DEFAULT_TARIFFS]
    out = []
    for item in saved:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        t = dict(TARIFF_DEFAULTS, **known.get(item["id"], {}))
        t.update(item)
        if t["id"] == "mentor":
            t.setdefault("mentor", True)
            if t.get("title") == "С наставником":     # старое название — теперь «VIP Резидент»
                t["title"] = "VIP Резидент"
        out.append(t)
    return out or [dict(t) for t in texts.DEFAULT_TARIFFS]


async def compare_rows() -> list[dict]:
    saved = await db.get_setting("compare")
    rows = saved if isinstance(saved, list) and saved else texts.DEFAULT_COMPARE
    return [{"label": str(r.get("label", ""))[:80], "cells": dict(r.get("cells") or {}), "default": str(r.get("default", "+"))[:40]}
            for r in rows if isinstance(r, dict) and r.get("label")]


async def tariff(tid: str) -> dict | None:
    return next((t for t in await tariffs() if t["id"] == tid), None)


def week_start(ts: int | None = None) -> int:
    d = dt.datetime.fromtimestamp(ts or time.time(), MSK)
    monday = (d - dt.timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


async def seats_left(t: dict) -> int:
    """Сколько мест осталось на этой неделе. Без ограничения — 9999."""
    seats = int(t.get("weekly_seats") or 0)
    if seats <= 0:
        return 9999
    return max(0, seats - await db.seats_taken(t["id"], week_start()))


# ---------- Закрытая группа ----------

async def group_status(uid: int) -> bool | None:
    """True/False — состоит ли в группе; None — группа не настроена или бот не смог проверить."""
    if not config.GROUP_ID:
        return None
    try:
        member = await bot.get_chat_member(config.GROUP_ID, uid)
    except TelegramAPIError as exc:
        if "user not found" in str(exc).lower() or "participant_id_invalid" in str(exc).lower():
            return False
        log.warning("Не удалось проверить участника %s: %s", uid, exc)
        return None
    status = getattr(member, "status", "")
    status = getattr(status, "value", status)
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


async def refresh_group(user: dict, force: bool = False) -> dict:
    """Перепроверяет членство в группе (не чаще раза в 30 минут без force)."""
    if not config.GROUP_ID:
        return user
    if not force and time.time() - int(user.get("group_checked") or 0) < 1800:
        return user
    status = await group_status(user["id"])
    if status is None:
        return user
    was = bool(user.get("group_member"))
    await db.update_user(user["id"], group_member=int(status), group_checked=int(time.time()))
    user = dict(user, group_member=int(status), group_checked=int(time.time()))
    if status != was:
        await sync_modules(user)
    return user


async def invite_link(uid: int) -> str | None:
    if not config.GROUP_ID:
        return None
    try:
        link = await bot.create_chat_invite_link(
            config.GROUP_ID, name=f"cc-{uid}"[:32], member_limit=1,
            expire_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2),
        )
        return link.invite_link
    except TelegramAPIError as exc:
        log.warning("Не удалось создать ссылку в группу: %s", exc)
        return None


async def remember_chat(chat_id: int, title: str = "") -> None:
    """Группы и чаты, где бот админ: из них убираем людей, когда доступ закрыт."""
    if not chat_id or chat_id == await channel_id():
        return
    chats = await db.get_setting("chats", {}) or {}
    if str(chat_id) not in chats:
        chats[str(chat_id)] = {"title": title[:80]}
        await db.set_setting("chats", chats)


async def resident_chats() -> set[int]:
    chats = await db.get_setting("chats", {}) or {}
    ids = {int(k) for k in chats if re.fullmatch(r"-?\d+", str(k))}
    ids |= {c for c in (config.GROUP_ID, config.CHAT_ID) if c}
    ids.discard(await channel_id() or 0)
    return ids


async def kick(uid: int) -> None:
    """Закончился или закрыт доступ — убираем из закрытой группы и чата резидентов (без бана навсегда)."""
    if config.is_admin_user(uid):
        return
    for chat in await resident_chats():
        try:
            member = await bot.get_chat_member(chat, uid)
            status = getattr(member.status, "value", member.status)
            if status in ("left", "kicked"):
                continue
            await bot.ban_chat_member(chat, uid, until_date=dt.timedelta(seconds=60))
            await bot.unban_chat_member(chat, uid, only_if_banned=True)
        except TelegramAPIError as exc:
            log.info("Не удалось убрать %s из чата %s: %s", uid, chat, exc)


# ---------- Обязательная подписка на канал ----------

async def channel_id() -> int | None:
    if config.CHANNEL_ID:
        return config.CHANNEL_ID
    saved = await db.get_setting("channel_id", 0)
    return int(saved) if saved else None


CHANNEL_RECHECK = 6 * 3600


async def channel_ok(user: dict | None, force: bool = False) -> bool:
    """Подписан на канал или подал заявку. Без канала в настройках — проверки нет."""
    if not user:
        return False
    chat = await channel_id()
    if not chat or config.is_admin_user(user["id"], user.get("username")):
        return True
    if not force and time.time() - int(user.get("channel_ok_at") or 0) < CHANNEL_RECHECK:
        return True
    try:
        member = await bot.get_chat_member(chat, user["id"])
        status = getattr(member.status, "value", member.status)
        inside = status in ("creator", "administrator", "member") or (
            status == "restricted" and getattr(member, "is_member", False))
    except TelegramAPIError as exc:
        log.info("Не удалось проверить подписку %s: %s", user["id"], exc)
        return True   # бот не админ в канале — не запираем людей из-за настроек
    if inside or user.get("channel_requested"):
        await db.update_user(user["id"], channel_ok_at=int(time.time()))
        return True
    return False


def gate_markup():
    return keyboard([InlineKeyboardButton(text="Подать заявку в канал", url=config.CHANNEL_LINK)],
                    [InlineKeyboardButton(text="Я подписался", callback_data="gate:check")])


GATE_TEXT = ("Чтобы пользоваться ботом, подпишись на канал <b>{name}</b>: там гайды, промпты и разборы.\n\n"
             "Нажми «Подать заявку в канал» — я увижу заявку и сразу открою приложение.")


async def send_gate(uid: int) -> None:
    await send(uid, GATE_TEXT.format(name=html.escape(config.CHANNEL_NAME)), gate_markup())


async def members_count() -> int:
    """Сколько участников в C&C Family: ручное число из админки, иначе — участники группы, иначе — резиденты."""
    manual = await db.get_setting("members_manual", 0)
    if manual:
        return int(manual)
    if time.time() - _members_cache["at"] < 600 and _members_cache["value"]:
        return int(_members_cache["value"])
    value = 0
    if config.GROUP_ID:
        try:
            value = await bot.get_chat_member_count(config.GROUP_ID)
        except TelegramAPIError as exc:
            log.info("Не удалось узнать число участников группы: %s", exc)
    if not value:
        value = await db.residents_count()
    _members_cache.update(value=value, at=time.time())
    return int(value)


# ---------- Парсер, скрипты, оценки ----------

async def sync_modules(user: dict) -> None:
    """Резидент получает полный доступ к парсеру (и его скриптам); без доступа — снова пробный режим.
    Доступ, выданный в админке самого парсера, ядро не трогает."""
    from modules.parser import db as parser_db

    resident = db.is_resident(user)
    try:
        if resident and not user.get("modules_synced"):
            await parser_db.grant_member(user["id"])
            await db.update_user(user["id"], modules_synced=1)
        elif not resident and user.get("modules_synced"):
            await parser_db.set_approved(user["id"], 0)
            await db.update_user(user["id"], modules_synced=0)
    except Exception:
        log.exception("Не удалось обновить доступ в модулях для %s", user["id"])


async def add_eval_credits(user: dict, amount: int) -> None:
    if amount <= 0:
        return
    from modules.evaluation import db as eval_db
    try:
        await eval_db.upsert_user(user["id"], user.get("username"), user.get("first_name"))
        await eval_db.add_credits(user["id"], amount)
    except Exception:
        log.exception("Не удалось добавить оценки %s", user["id"])


# ---------- Выдача и окончание доступа ----------

async def approve_join(uid: int) -> bool:
    """Человек подал заявку в группу раньше, чем оплатил, — одобряем её."""
    if not config.GROUP_ID:
        return False
    try:
        await bot.approve_chat_join_request(config.GROUP_ID, uid)
        await db.update_user(uid, join_requested=0)
        return True
    except TelegramAPIError as exc:
        log.info("Заявку %s не одобрить: %s", uid, exc)
        await db.update_user(uid, join_requested=0)
        return False


async def approve_chat(user: dict) -> bool:
    """Человек подал заявку в чат резидентов до оплаты — одобряем её."""
    chat = user.get("chat_requested") or 0
    if not chat:
        return False
    try:
        await bot.approve_chat_join_request(chat, user["id"])
        return True
    except TelegramAPIError as exc:
        log.info("Заявку %s в чат не одобрить: %s", user["id"], exc)
        return False
    finally:
        await db.update_user(user["id"], chat_requested=0)


async def grant(uid: int, tariff_id: str, days: int, notify: bool = True, eval_credits: int | None = None) -> dict:
    user = await db.extend_access(uid, tariff_id, days)
    return await after_grant(user, tariff_id, notify, eval_credits)


async def grant_until(uid: int, tariff_id: str, until: int, notify: bool = True, eval_credits: int | None = None) -> dict:
    user = await db.access_until(uid, tariff_id, until)
    return await after_grant(user, tariff_id, notify, eval_credits)


async def after_grant(user: dict, tariff_id: str, notify: bool, eval_credits: int | None) -> dict:
    uid = user["id"]
    await sync_modules(user)
    await add_eval_credits(user, config.EVAL_RESIDENT_CREDITS if eval_credits is None else eval_credits)
    _members_cache["at"] = 0
    if notify:
        until = "Доступ навсегда." if user["access_forever"] else f"Доступ до {fmt_date(user['access_until'])}."
        # Заявки, поданные до оплаты, одобряем сразу. Остальным — кнопки со ссылками-заявками: бот одобрит сам.
        group_in = False
        if config.GROUP_ID:
            group_in = await group_status(uid)
            if not group_in and user.get("join_requested"):
                group_in = await approve_join(uid)
        chat_in = await approve_chat(user)
        group_link = config.GROUP_LINK or (await invite_link(uid) if config.GROUP_ID else None)
        markup = keyboard(
            [InlineKeyboardButton(text="Закрытая группа", url=group_link) if group_link and not group_in else None,
             InlineKeyboardButton(text="Чат резидентов", url=config.CHAT_LINK) if config.CHAT_LINK and not chat_in else None],
            [app_button("Открыть C&C")],
        )
        body = await text("paid", until=until)
        if group_in and chat_in:
            body += "\n\nЗаявки в группу и чат одобрил — ты уже внутри."
        elif group_in:
            body += "\n\nЗаявку в закрытую группу одобрил — ты уже внутри."
        elif chat_in:
            body += "\n\nЗаявку в чат резидентов одобрил — ты уже внутри."
        await send(uid, body, markup, image="paid")
    tinfo = await tariff(tariff_id) or {}
    if tinfo.get("mentor") or tariff_id == "mentor":
        who = f"@{user['username']}" if user.get("username") else (user.get("first_name") or str(uid))
        for admin_id in config.ADMIN_IDS:
            await send(admin_id, f"<b>Новый ученик с наставником</b>: {who} (<code>{uid}</code>). Свяжитесь с ним.")
    return user


async def revoke(uid: int, notify: bool = False) -> None:
    await db.revoke_access(uid)
    user = await db.get_user(uid)
    if user:
        await sync_modules(user)
    await kick(uid)
    _members_cache["at"] = 0
    if notify:
        await send(uid, await text("expired"), keyboard([app_button("Тарифы", "#join")]))


async def process_expiry() -> None:
    soon = int(time.time()) + 3 * 86400
    for user in await db.users_to_warn(soon):
        await db.update_user(user["id"], expiry_warned=1)
        if user.get("started") and not user.get("blocked_bot"):
            await send(user["id"], await text("expiring", date=fmt_date(user["access_until"])),
                       keyboard([app_button("Продлить", "#join")]))
    for user in await db.users_expired():
        await db.update_user(user["id"], expired_done=1, expiry_warned=0)
        if config.is_admin_user(user["id"], user.get("username")):
            continue
        fresh = dict(user, group_member=0)
        await kick(user["id"])
        await db.update_user(user["id"], group_member=0)
        await sync_modules(fresh)
        if user.get("started") and not user.get("blocked_bot"):
            await send(user["id"], await text("expired"), keyboard([app_button("Тарифы", "#join")]))
    _members_cache["at"] = 0


async def process_abandoned() -> None:
    """Открыл оплату и за 3 минуты не оплатил — одно мягкое напоминание (не чаще раза в сутки)."""
    cutoff = int(time.time()) - config.CHECKOUT_REMINDER_SECONDS
    seen: set[int] = set()
    for payment in await db.abandoned_checkouts(cutoff):
        uid = payment["user_id"]
        if uid in seen:
            continue
        seen.add(uid)
        await db.mark_reminded(uid)
        user = await db.get_user(uid)
        if not user or db.is_resident(user) or await db.paid_after(uid, payment["created_at"]):
            continue
        if time.time() - int(user.get("abandon_at") or 0) < 86400:
            continue
        await db.update_user(uid, abandon_at=int(time.time()))
        markup = keyboard([app_button("Открыть C&C", "#join")],
                          [url_button("Написать лично", config.PERSONAL_USERNAME)])
        await send(uid, await text("abandoned"), markup, image="help")


async def process_marathon() -> None:
    """Утром (с 10 до 21 по Москве) напоминает про открывшийся день марафона."""
    hour = dt.datetime.now(MSK).hour
    if not 10 <= hour < 21:
        return
    from .content import marathon_state

    for uid in await db.marathon_participants():
        user = await db.get_user(uid)
        if not user or not user.get("started") or user.get("blocked_bot") or not user.get("notify"):
            continue
        state = await marathon_state(uid)
        current = state.get("current")
        if not current or not current.get("open") or current.get("done"):
            continue
        if int(user.get("marathon_notified") or 0) >= current["day"]:
            continue
        await db.update_user(uid, marathon_notified=current["day"])
        await send(uid, await text("marathon_day", day=current["day"], title=current["title"]),
                   keyboard([app_button("Открыть день", "#marathon")]))


async def loop(name: str, func, every: float) -> None:
    await asyncio.sleep(5)
    while True:
        try:
            await func()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Фоновая задача %s упала, повторю", name)
        await asyncio.sleep(every)
