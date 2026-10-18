"""Настройки C&C Family. Всё берётся из переменных окружения (Railway → Variables) или файла .env."""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip() or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "on", "да")


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Юзернейм бота без @. Нужен для ссылок вида t.me/бот?startapp=… (уточняется при запуске).
BOT_USERNAME = os.getenv("BOT_USERNAME", "CodeAndCash_bot").strip().lstrip("@")

# Админы: числовые Telegram ID и/или @username через запятую.
_admin_values = [v.strip() for v in re.split(r"[,;\s]+", os.getenv("ADMIN_IDS", "")) if v.strip()]
_USERNAME_RE = r"@?[A-Za-z][A-Za-z0-9_]{3,31}"
ADMIN_IDS = {int(v) for v in _admin_values if v.isdigit() and int(v) > 0}
ADMIN_USERNAMES = {v.lstrip("@").lower() for v in _admin_values if not v.isdigit() and re.fullmatch(_USERNAME_RE, v)}


def is_admin_user(user_id: int | None, username: str | None = None) -> bool:
    if user_id and int(user_id) in ADMIN_IDS:
        return True
    return bool(username) and username.lstrip("@").lower() in ADMIN_USERNAMES


# Публичный HTTPS-адрес сервера (Railway → Settings → Domains). Можно и старым именем WEBAPP_URL.
PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip()
API_PORT = _int("PORT", _int("API_PORT", 8080, 1, 65535), 1, 65535)

# Все базы лежат в одной папке. На Railway — подключённое хранилище /data, чтобы ничего не стиралось.
_data = Path(os.getenv("DATA_DIR", "./data")).expanduser()
DATA_DIR = _data if _data.is_absolute() else ROOT_DIR / _data
CORE_DB = DATA_DIR / "family.db"
PARSER_DB = DATA_DIR / "parser.db"
EVAL_DB = DATA_DIR / "evaluation.db"

BRAND = "C&C Family"
# «Поддержка» и «Написать лично» — без @.
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "SUN9ISE").strip().lstrip("@")
PERSONAL_USERNAME = os.getenv("PERSONAL_USERNAME", "").strip().lstrip("@") or SUPPORT_USERNAME

# Закрытая группа резидентов: ID вида -100…  Бот должен быть в ней админом
# с правами «Пригласительные ссылки» и «Блокировка участников».
_group = os.getenv("GROUP_ID", "").strip()
GROUP_ID = int(_group) if re.fullmatch(r"-?\d+", _group) else None
# Общая ссылка в группу (с заявками). Резидентам бот одобряет заявку сам.
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/+K5c7BUflUlozNTQx").strip()
# Чат резидентов (общение, помощь, результаты). Ссылка с заявками: кнопка «Подать заявку» видна только резидентам,
# бот одобряет их заявки сам. CHAT_ID бот пришлёт админам, когда его добавят в чат админом.
# Обязательная подписка: пока человек не подписан на канал (или не подал заявку), бот и приложение не работают.
# Бот должен быть админом канала. CHANNEL_ID бот запомнит сам, когда его добавят в канал (можно задать и вручную).
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/+pKQkkgH4l-M4NGEx").strip()
_channel = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(_channel) if re.fullmatch(r"-?\d+", _channel) else None
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Code & Cash").strip()
CHAT_LINK = os.getenv("CHAT_LINK", "https://t.me/+wvw9cMktwFphYjgx").strip()
_chat = os.getenv("CHAT_ID", "").strip()
CHAT_ID = int(_chat) if re.fullmatch(r"-?\d+", _chat) else None

# ---- Оплата ----
# Крипта: @CryptoBot → Crypto Pay → Create App → токен.
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
CRYPTO_PAY_TESTNET = _flag("CRYPTO_PAY_TESTNET")
CRYPTO_ASSETS = os.getenv("CRYPTO_ASSETS", "USDT,TON,BTC").strip()
# Крипта через xRocket: @xrocket → Rocket Pay → Создать → API токен. Счёт выставляется в USDT по цене тарифа в $.
XROCKET_PAY_TOKEN = os.getenv("XROCKET_PAY_TOKEN", "").strip()
XROCKET_CURRENCY = os.getenv("XROCKET_CURRENCY", "USDT").strip().upper() or "USDT"
# AI-оценка работ: ключ Claude (console.anthropic.com) или OpenRouter (openrouter.ai). Без ключа — только оценка командой.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()  # другой OpenAI-совместимый сервис вместо OpenRouter
# Оплата картой через менеджера: кнопка «Оплатить картой» открывает эту ссылку (можно поменять в админке → Ещё).
CARD_PAY_LINK = os.getenv("CARD_PAY_LINK", "https://t.me/m/KXcCg7quZGFh").strip()
# Карта: токен платёжного провайдера из @BotFather → Payments (ЮKassa, Robokassa и др.).
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "").strip()
CARD_CURRENCY = os.getenv("CARD_CURRENCY", "RUB").strip().upper() or "RUB"
# Чек по 54-ФЗ (нужен для ЮKassa): Telegram спросит почту и передаст её кассе.
CARD_RECEIPT = _flag("CARD_RECEIPT")
CARD_VAT_CODE = _int("CARD_VAT_CODE", 1, 1, 12)  # 1 — без НДС
# Карта через Tribute: Creator Dashboard → Settings → API Keys. Ссылки на товары — у тарифов в админке.
TRIBUTE_API_KEY = os.getenv("TRIBUTE_API_KEY", "").strip()
# Звёзды Telegram — запасной способ, включается отдельно.
STARS_ENABLED = _flag("STARS_ENABLED")

# Через сколько секунд напомнить, если человек открыл оплату и не оплатил.
CHECKOUT_REMINDER_SECONDS = _int("CHECKOUT_REMINDER_SECONDS", 180, 30, 86400)
# Сколько оценок работ добавить резиденту при каждой оплате.
EVAL_RESIDENT_CREDITS = _int("EVAL_RESIDENT_CREDITS", 3, 0, 100)

# Меняется при каждом обновлении мини-аппа — телефон забывает старую копию.
APP_VERSION = "1.4.0"


def join_url() -> str:
    """Ссылка «вступить»: открывает мини-апп сразу на тарифах."""
    return f"https://t.me/{BOT_USERNAME}?startapp=join"


def app_url(path: str = "") -> str:
    return PUBLIC_URL + "/" + path.lstrip("/") if PUBLIC_URL else ""


def validate_config() -> None:
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN. Добавьте его в переменные Railway (или в .env).")
    if not (ADMIN_IDS or ADMIN_USERNAMES):
        raise RuntimeError("Не заданы ADMIN_IDS: укажите Telegram ID и/или @username админов.")
    if PUBLIC_URL and not PUBLIC_URL.startswith("https://"):
        raise RuntimeError("PUBLIC_URL должен начинаться с https://")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
