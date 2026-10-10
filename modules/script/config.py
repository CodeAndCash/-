import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Администраторы: числовые Telegram ID и/или @username, через запятую, пробел или «;».
_admin_values = [
    value.strip()
    for value in re.split(r"[,;\s]+", os.getenv("ADMIN_IDS", "") + " " + os.getenv("ADMIN_USERNAMES", ""))
    if value.strip()
]
_USERNAME_RE = r"@?[A-Za-z][A-Za-z0-9_]{3,31}"
ADMIN_IDS = {int(v) for v in _admin_values if v.isdigit() and int(v) > 0}
ADMIN_USERNAMES = {
    v.lstrip("@").lower() for v in _admin_values if not v.isdigit() and re.fullmatch(_USERNAME_RE, v)
}
ADMIN_IDS_INVALID = [v for v in _admin_values if not v.isdigit() and not re.fullmatch(_USERNAME_RE, v)]


def is_admin_user(user_id: int | None, username: str | None = None) -> bool:
    """Админ — если его ID или @username указан в ADMIN_IDS / ADMIN_USERNAMES."""
    if user_id and int(user_id) in ADMIN_IDS:
        return True
    return bool(username) and username.lstrip("@").lower() in ADMIN_USERNAMES


from cc import config as _cc  # общие настройки C&C Family

# Скрипты живут внутри общего мини-аппа по адресу /script/
WEBAPP_URL = _cc.app_url("script/")
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip()
API_PORT = int(os.getenv("PORT") or os.getenv("API_PORT", "8080"))

DB_PATH = _cc.SCRIPT_DB


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


# Нейросеть: Google Gemini (бесплатный уровень, ключ без карты).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# Любая нейросеть с OpenAI-совместимым API. Достаточно AI_PROVIDER и AI_API_KEY.
AI_PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
}
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
_preset = AI_PRESETS.get(AI_PROVIDER, AI_PRESETS["groq"])
AI_BASE_URL = (os.getenv("AI_BASE_URL", "").strip() or _preset[0]).rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "").strip() or _preset[1]
AI_ENABLED = bool(AI_API_KEY or GEMINI_API_KEY)
AI_DAILY_LIMIT = _int("AI_DAILY_LIMIT", 900, 0, 100000)
AI_USER_DAILY_LIMIT = _int("AI_USER_DAILY_LIMIT", 30, 0, 1000)

# Доступ: пробные генерации для всех и дневной лимит участников C&C Family.
TRIAL_GENERATIONS = _int("TRIAL_GENERATIONS", 3, 0, 100)
MEMBER_DAILY_LIMIT = _int("MEMBER_DAILY_LIMIT", 20, 1, 5000)
JOIN_URL = _cc.join_url()
CONTACT_USERNAME = _cc.SUPPORT_USERNAME


def validate_config() -> None:
    if (
        not BOT_TOKEN
        or ":" not in BOT_TOKEN
        or "your_bot_token" in BOT_TOKEN.lower()
        or "..." in BOT_TOKEN
    ):
        raise RuntimeError(
            "Не задан BOT_TOKEN. Создайте файл .env по образцу .env.example "
            "и вставьте токен от BotFather."
        )
    if WEBAPP_URL:
        try:
            parsed = urlsplit(WEBAPP_URL)
            ok = parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
        except ValueError:
            ok = False
        if not ok:
            raise RuntimeError("WEBAPP_URL должен быть публичным HTTPS-адресом Mini App.")
    if ADMIN_IDS_INVALID:
        import logging

        logging.getLogger("script_cc").warning(
            "ADMIN_IDS: пропущены непонятные значения: %s", ", ".join(ADMIN_IDS_INVALID)
        )
    if not 1 <= API_PORT <= 65535:
        raise RuntimeError("API_PORT должен быть числом от 1 до 65535.")
