import asyncio
import html
import logging
import re
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from . import db
from .config import (
    CONTACT_USERNAME,
    TRIAL_GENERATIONS,
    WEBAPP_URL,
    is_admin_user,
)

from cc.tg import bot  # один общий бот C&C Family
dp = Router(name="script")  # обработчиков нет: всё общение — через мини-апп
log = logging.getLogger("script_cc.bot")


def app_keyboard() -> InlineKeyboardMarkup:
    if not WEBAPP_URL:
        raise RuntimeError("Сначала укажите WEBAPP_URL.")
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть Script C&C", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )


def is_admin(user_id: int, username: str | None = None) -> bool:
    return is_admin_user(user_id, username)


def _num(value: str, signed: bool = False) -> int | None:
    """Число из аргумента команды или None (защита от «--5», «²» и т.п.)."""
    if re.fullmatch(r"-?\d{1,9}" if signed else r"\d{1,9}", value or ""):
        return int(value)
    return None


def _gen_word(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "генерация"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "генерации"
    return "генераций"


TRIAL_OVER = (
    "<b>Пробный доступ закончился</b>\n\n"
    "Вы использовали <b>{used} {word}</b>.\n\n"
    "Чтобы продолжить создавать скрипты и пользоваться библиотекой Script C&amp;C, вступите в команду "
    "<b>C&amp;C Family</b> — подробности можно узнать у @{contact}."
)


def trial_keyboard() -> InlineKeyboardMarkup:
    from cc import config as _cc
    rows = []
    if _cc.PUBLIC_URL:
        rows.append([InlineKeyboardButton(text="Вступить в C&C Family", web_app=WebAppInfo(url=_cc.app_url("#join")))])
    rows.append([InlineKeyboardButton(text="Докупить генерации", url=f"https://t.me/{CONTACT_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


ASSETS = Path(__file__).with_name("assets")
IMAGES = {"closed": ASSETS / "access_closed.jpg", "open": ASSETS / "access_open.jpg"}
_file_ids: dict[str, str] = {}  # после первой загрузки Telegram отдаёт file_id — шлём его

BANNED_TEXT = f"<b>Вы забанены</b>, свяжитесь с @{CONTACT_USERNAME}\n\nЧтобы узнать причину."
ACCESS_CLOSED_TEXT = (
    "<b>Полный доступ к Script C&amp;C закрыт</b>\n\n" f"Подробности можно узнать у @{CONTACT_USERNAME}."
)


def access_open_text(limit: int | None = None, bonus: int = 0, by_key: bool = False) -> str:
    title = "Ключ активирован" if by_key else "Полный доступ к Script C&amp;C открыт"
    parts = [f"<b>{title}</b>", "Добро пожаловать в <b>C&amp;C Family</b>!"]
    gained = []
    if limit:
        gained.append(f"<b>{limit} {_gen_word(limit)} в день</b>")
    if bonus:
        gained.append(f"<b>+{bonus}</b> бонусных генераций")
    if gained:
        parts.append("Вам доступно: " + ", ".join(gained) + ".")
    parts.append("Откройте приложение и создавайте скрипты 👇" if WEBAPP_URL else "Откройте приложение и создавайте скрипты.")
    return "\n\n".join(parts)


async def send_picture(user_id: int, kind: str, text: str, reply_markup=None) -> None:
    """Картинка CLOSE/OPEN вместе с текстом. Если картинки нет — просто текст."""
    path = IMAGES.get(kind)
    if not path or not path.exists():
        await bot.send_message(user_id, text, reply_markup=reply_markup)
        return
    cached = _file_ids.get(kind)
    try:
        sent = await bot.send_photo(user_id, cached or FSInputFile(path), caption=text, reply_markup=reply_markup)
    except TelegramAPIError as exc:
        if "blocked" in str(exc).lower() or "chat not found" in str(exc).lower():
            raise
        log.warning("Photo %s failed (%s), retrying", kind, exc)
        _file_ids.pop(kind, None)
        try:
            sent = await bot.send_photo(user_id, FSInputFile(path), caption=text, reply_markup=reply_markup)
        except TelegramAPIError:
            await bot.send_message(user_id, text, reply_markup=reply_markup)
            return
    if getattr(sent, "photo", None):
        _file_ids[kind] = sent.photo[-1].file_id


async def send_trial_over(user_id: int, used: int = TRIAL_GENERATIONS) -> None:
    await send_picture(
        user_id, "closed",
        TRIAL_OVER.format(used=used, word=_gen_word(used), contact=CONTACT_USERNAME),
        reply_markup=trial_keyboard(),
    )


async def send_access_opened(user_id: int, limit: int | None = None, bonus: int = 0, by_key: bool = False) -> None:
    if limit is None:
        row = await db.get_user(user_id)
        limit = row["daily_limit"] if row else None
    await send_picture(
        user_id, "open", access_open_text(limit, bonus, by_key),
        reply_markup=app_keyboard() if WEBAPP_URL else None,
    )


async def send_access_closed(user_id: int) -> None:
    await send_picture(user_id, "closed", ACCESS_CLOSED_TEXT, reply_markup=trial_keyboard())


async def deny_admin(message: Message) -> None:
    await message.answer(
        "<b>Эта команда только для администратора</b>\n\n"
        f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
        "Если вы владелец — впишите этот ID (или свой @username) в переменную "
        "<code>ADMIN_IDS</code> и перезапустите сервис."
    )


async def _active_user(message: Message) -> dict | None:
    """Пользователь бота или None, если он заблокирован (ему уже отправлен ответ)."""
    user = message.from_user
    row = await db.upsert_user(user.id, user.username, user.first_name)
    if row.get("banned") and not is_admin(user.id, user.username):
        await send_picture(user.id, "closed", BANNED_TEXT)
        return None
    return row


def _access_line(row: dict) -> str:
    if db.is_member(row):
        return f"<b>Ваш доступ:</b> полный, {row['daily_limit']} {_gen_word(row['daily_limit'])} в день."
    left = db.trial_left(row)
    if left > 0:
        return f"<b>Ваш доступ:</b> пробный — {left} {_gen_word(left)}."
    return "<b>Ваш доступ:</b> пробный доступ закончился."


CAPTION_LIMIT = 1024


def _plain_len(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


async def broadcast_to_all(text: str, image: bytes | None = None) -> tuple[int, int]:
    """Рассылка всем незаблокированным. text — уже безопасный HTML (теги Telegram).
    Картинка уходит с подписью; длинный текст (больше 1024 символов) — отдельным сообщением."""
    ids = await db.broadcast_ids()
    sent = 0
    text = (text or "").strip()
    photo_id = None
    caption_fits = image is not None and _plain_len(text) <= CAPTION_LIMIT
    for user_id in ids:
        try:
            if image is not None:
                photo = photo_id or BufferedInputFile(image, filename="broadcast.jpg")
                msg = await bot.send_photo(user_id, photo, caption=text if caption_fits and text else None)
                if msg.photo:
                    photo_id = msg.photo[-1].file_id
                if text and not caption_fits:
                    await bot.send_message(user_id, text)
            else:
                await bot.send_message(user_id, text)
            sent += 1
        except TelegramAPIError:
            log.info("Broadcast failed for user %s", user_id)
        await asyncio.sleep(0.05)
    return sent, len(ids)
