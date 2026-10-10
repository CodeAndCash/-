import asyncio
import html
import re
import logging
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
    is_admin_user,
    CONTACT_USERNAME,
    TRIAL_LEADS,
    TRIAL_SEARCHES,
    WEBAPP_URL,
)

from cc.tg import bot  # один общий бот C&C Family
dp = Router(name="parser")  # обработчиков нет: всё общение — через мини-апп
log = logging.getLogger("parser_cc.bot")


def app_keyboard() -> InlineKeyboardMarkup:
    if not WEBAPP_URL:
        raise RuntimeError("Сначала укажите WEBAPP_URL в файле .env.")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Parser C&C",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )


def is_admin(user_id: int, username: str | None = None) -> bool:
    return is_admin_user(user_id, username)


def _num(value: str, signed: bool = False) -> int | None:
    """Число из аргумента команды или None (защита от «--5», «²» и т.п.)."""
    if re.fullmatch(r"-?\d{1,9}" if signed else r"\d{1,9}", value or ""):
        return int(value)
    return None


def _lead_word(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "лид"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "лида"
    return "лидов"


TRIAL_OVER = (
    "<b>Пробный доступ закончился</b>\n\n"
    "Вы использовали пробный запрос и нашли <b>{found} {word}</b>.\n\n"
    "Чтобы продолжить получать лиды и пользоваться Parser C&amp;C, вступите в команду "
    "<b>C&amp;C Family</b> — подробности можно узнать у @{contact}."
)


def trial_keyboard() -> InlineKeyboardMarkup:
    from cc import config as _cc
    rows = []
    if _cc.PUBLIC_URL:
        rows.append([InlineKeyboardButton(text="Вступить в C&C Family", web_app=WebAppInfo(url=_cc.app_url("#join")))])
    rows.append([InlineKeyboardButton(text="Докупить запросы", url=f"https://t.me/{CONTACT_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


ASSETS = Path(__file__).with_name("assets")
IMAGES = {"closed": ASSETS / "access_closed.jpg", "open": ASSETS / "access_open.jpg"}
_file_ids: dict[str, str] = {}  # после первой загрузки Telegram отдаёт file_id — шлём его

BANNED_TEXT = f"<b>Вы забанены</b>, свяжитесь с @{CONTACT_USERNAME}\n\nЧтобы узнать причину."
ACCESS_CLOSED_TEXT = (
    "<b>Полный доступ к Parser C&amp;C закрыт</b>\n\n"
    f"Подробности можно узнать у @{CONTACT_USERNAME}."
)


def access_open_text(limit: int | None = None, bonus: int = 0, by_key: bool = False) -> str:
    title = "Ключ активирован" if by_key else "Полный доступ к Parser C&amp;C открыт"
    parts = [f"<b>{title}</b>", "Добро пожаловать в <b>C&amp;C Family</b>!"]
    gained = []
    if limit:
        gained.append(f"<b>{limit} {_lead_word(limit)} в день</b>")
    if bonus:
        gained.append(f"<b>+{bonus}</b> поисковых запросов")
    if gained:
        parts.append("Вам доступно: " + ", ".join(gained) + ".")
    parts.append("Откройте приложение и начинайте искать клиентов 👇" if WEBAPP_URL else "Откройте приложение и начинайте искать клиентов.")
    return "\n\n".join(parts)


# Совместимость со старым кодом
ACCESS_OPEN_TEXT = access_open_text()


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
            # старый file_id мог устареть — отправляем файл заново
            sent = await bot.send_photo(user_id, FSInputFile(path), caption=text, reply_markup=reply_markup)
        except TelegramAPIError:
            # картинка не ушла — текст всё равно должен дойти
            await bot.send_message(user_id, text, reply_markup=reply_markup)
            return
    if getattr(sent, "photo", None):
        _file_ids[kind] = sent.photo[-1].file_id


async def send_trial_over(user_id: int, found: int = TRIAL_LEADS) -> None:
    await send_picture(
        user_id, "closed",
        TRIAL_OVER.format(found=found, word=_lead_word(found), contact=CONTACT_USERNAME),
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
    """Не‑админ вызвал админ‑команду: объясняем, а не молчим."""
    await message.answer(
        "<b>Эта команда только для администратора</b>\n\n"
        f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
        "Если вы владелец — впишите этот ID (или свой @username) в переменную "
        "<code>ADMIN_IDS</code> в Railway и нажмите Redeploy."
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
        return f"<b>Ваш доступ:</b> полный, {row['daily_limit']} {_lead_word(row['daily_limit'])} в день."
    left = db.trial_left(row, TRIAL_SEARCHES)
    if left > 0:
        return f"<b>Ваш доступ:</b> пробный — {left} запрос, до {TRIAL_LEADS} лидов."
    return "<b>Ваш доступ:</b> пробный доступ закончился."


CAPTION_LIMIT = 1024


def _plain_len(text: str) -> int:
    import re

    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


async def broadcast_to_approved(text: str, image: bytes | None = None) -> tuple[int, int]:
    """Рассылка всем незаблокированным. text — уже безопасный HTML (теги Telegram).
    Картинка уходит с подписью; длинный текст (больше 1024 символов) — отдельным сообщением."""
    ids = await db.approved_ids()
    sent = 0
    text = (text or "").strip()
    photo_id = None
    caption_fits = image is not None and _plain_len(text) <= CAPTION_LIMIT
    for user_id in ids:
        try:
            if image is not None:
                photo = photo_id or BufferedInputFile(image, filename="broadcast.jpg")
                message = await bot.send_photo(
                    user_id, photo, caption=text if caption_fits and text else None
                )
                if message.photo:
                    photo_id = message.photo[-1].file_id
                if text and not caption_fits:
                    await bot.send_message(user_id, text)
            else:
                await bot.send_message(user_id, text)
            sent += 1
        except TelegramAPIError:
            log.info("Broadcast failed for user %s", user_id)
        await asyncio.sleep(0.05)
    return sent, len(ids)
