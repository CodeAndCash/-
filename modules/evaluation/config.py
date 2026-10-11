import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Админы: числовые Telegram ID и/или @username через запятую.
_admin_values = [v.strip() for v in re.split(r"[,;\s]+", os.getenv("ADMIN_IDS", "")) if v.strip()]
_USERNAME_RE = r"@?[A-Za-z][A-Za-z0-9_]{3,31}"
ADMIN_IDS = {int(v) for v in _admin_values if v.isdigit() and int(v) > 0}
ADMIN_USERNAMES = {v.lstrip("@").lower() for v in _admin_values if not v.isdigit() and re.fullmatch(_USERNAME_RE, v)}


def is_admin_user(user_id: int | None, username: str | None = None) -> bool:
    if user_id and int(user_id) in ADMIN_IDS:
        return True
    return bool(username) and username.lstrip("@").lower() in ADMIN_USERNAMES


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


from cc import config as _cc  # общие настройки C&C Family

# Админка оценок живёт внутри общего мини-аппа по адресу /eval
WEBAPP_URL = _cc.app_url("eval").rstrip("/")
# Меняется при каждом обновлении мини-аппа: новый адрес заставляет телефон
# забыть старую сохранённую копию страницы.
APP_VERSION = "10"
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip()
API_PORT = _int("PORT", _int("API_PORT", 8080, 1, 65535), 1, 65535)

DB_PATH = _cc.EVAL_DB

BRAND = "Оценка работ C&C"
FREE_REVIEWS = _int("FREE_REVIEWS", 2, 0, 100)
PRICE_RUB = _int("PRICE_RUB", 50, 1, 100000)
# Оплата внутри Telegram — звёздами (так Telegram требует для цифровых услуг).
PRICE_STARS = _int("PRICE_STARS", 35, 0, 100000)  # 0 — оплата звёздами выключена
# Кому писать, чтобы оплатить переводом (админ потом добавит оценку в мини-аппе).
PAY_CONTACT = _cc.SUPPORT_USERNAME
MAX_MEDIA = _int("MAX_MEDIA", 10, 1, 10)
# Платные оценки пока выключены: после бесплатных бот просто пишет, что оценки закончились.
# Включить: PAID_ENABLED=1 в переменных Railway.
PAID_ENABLED = bool(_int("PAID_ENABLED", 0, 0, 1))


def validate_config() -> None:
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN. Добавьте его в переменные Railway (или в .env).")
    if not (ADMIN_IDS or ADMIN_USERNAMES):
        raise RuntimeError("Не заданы ADMIN_IDS: укажите Telegram ID и/или @username админов.")
