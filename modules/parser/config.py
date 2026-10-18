import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Администраторы: числовые Telegram ID и/или @username, через запятую, пробел или «;».
# Пример: ADMIN_IDS=123456789, @SUN9ISE   (можно отдельно ADMIN_USERNAMES=SUN9ISE)
_admin_values = [
    value.strip() for value in re.split(r"[,;\s]+", os.getenv("ADMIN_IDS", "") + " " + os.getenv("ADMIN_USERNAMES", ""))
    if value.strip()
]
ADMIN_IDS = {int(value) for value in _admin_values if value.isdigit() and int(value) > 0}
ADMIN_USERNAMES = {
    value.lstrip("@").lower() for value in _admin_values
    if not value.isdigit() and re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value)
}
ADMIN_IDS_INVALID = [
    value for value in _admin_values
    if not value.isdigit() and not re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value)
]


def is_admin_user(user_id: int | None, username: str | None = None) -> bool:
    """Админ — если его ID или @username указан в ADMIN_IDS / ADMIN_USERNAMES."""
    if user_id and int(user_id) in ADMIN_IDS:
        return True
    return bool(username) and username.lstrip("@").lower() in ADMIN_USERNAMES


from cc import config as _cc  # общие настройки C&C Family

# Парсер живёт внутри общего мини-аппа по адресу /parser/
WEBAPP_URL = _cc.app_url("parser/")
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip()
API_PORT = int(os.getenv("PORT") or os.getenv("API_PORT", "8080"))

DB_PATH = _cc.PARSER_DB

def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


DEFAULT_LIMIT = _int("DEFAULT_LIMIT", 35, 1, 100000)
if DEFAULT_LIMIT == 70:
    # 70 — старое стандартное значение из прошлой инструкции; теперь стандарт 35.
    DEFAULT_LIMIT = 35
OVERPASS_URL = os.getenv(
    "OVERPASS_URL", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
).strip()
NOMINATIM_URL = os.getenv(
    "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
).strip()
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "you@example.com").strip()
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
GOOGLE_MAX_PAGES = _int("GOOGLE_MAX_PAGES", 3, 1, 3)
GOOGLE_MONTHLY_LIMIT = _int("GOOGLE_MONTHLY_LIMIT", 1000, 0, 10_000_000)

# 2ГИС Places API: ключ на dev.2gis.ru (демо-ключ или платный тариф с доступом к контактам).
DGIS_API_KEY = os.getenv("DGIS_API_KEY", "").strip()
DGIS_MONTHLY_LIMIT = _int("DGIS_MONTHLY_LIMIT", 5000, 0, 10_000_000)
DGIS_PAGE_SIZE = _int("DGIS_PAGE_SIZE", 10, 1, 50)
DGIS_MAX_PAGES = _int("DGIS_MAX_PAGES", 3, 1, 5)

# Geoapify Places: бесплатный тариф 3000 кредитов в день, карта не нужна.
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip()
GEOAPIFY_DAILY_CREDITS = _int("GEOAPIFY_DAILY_CREDITS", 2500, 0, 100000)

# Нейросеть для скриптов: Google Gemini API (бесплатный уровень, ключ без карты).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# Любая нейросеть с OpenAI-совместимым API: DeepSeek (платно, копейки), Groq и
# OpenRouter (есть бесплатные модели), OpenAI. Достаточно AI_PROVIDER и AI_API_KEY,
# адрес и модель подставятся сами (можно переопределить AI_BASE_URL / AI_MODEL).
AI_PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
}
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
_preset = AI_PRESETS.get(AI_PROVIDER, AI_PRESETS["deepseek"])
AI_BASE_URL = (os.getenv("AI_BASE_URL", "").strip() or _preset[0]).rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "").strip() or _preset[1]
AI_ENABLED = bool(AI_API_KEY or GEMINI_API_KEY)
AI_DAILY_LIMIT = _int("AI_DAILY_LIMIT", 900, 0, 100000)
AI_USER_DAILY_LIMIT = _int("AI_USER_DAILY_LIMIT", 30, 0, 1000)

# Проверка сайтов, Telegram и соцсетей бизнеса. По решению владельца выключена:
# выдаём бизнесы с телефоном и карточкой на карте, участник сам смотрит детали.
ANALYZE_SITES = os.getenv("ANALYZE_SITES", "0").strip().lower() in ("1", "true", "yes")

# Пробный доступ: у каждого нового пользователя TRIAL_SEARCHES поисков по TRIAL_LEADS лидов.
TRIAL_SEARCHES = _int("TRIAL_SEARCHES", 1, 0, 100)
TRIAL_LEADS = _int("TRIAL_LEADS", 10, 1, 200)
JOIN_URL = _cc.join_url()
CONTACT_USERNAME = _cc.SUPPORT_USERNAME

USER_AGENT = f"ParserCC/2.0 (Telegram Mini App; contact: {CONTACT_EMAIL})"


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
            parsed_url = urlsplit(WEBAPP_URL)
            valid_webapp_url = (
                parsed_url.scheme == "https"
                and bool(parsed_url.hostname)
                and not parsed_url.username
                and not parsed_url.password
            )
        except ValueError:
            valid_webapp_url = False
        if not valid_webapp_url:
            raise RuntimeError(
                "WEBAPP_URL должен быть публичным HTTPS-адресом Mini App. "
                "Оставьте поле пустым на первом запуске и следуйте README.md."
            )
    if ADMIN_IDS_INVALID:
        # Не роняем бота из‑за опечатки: просто пропускаем непонятные значения.
        import logging
        logging.getLogger("parser_cc").warning(
            "ADMIN_IDS: пропущены непонятные значения: %s", ", ".join(ADMIN_IDS_INVALID)
        )
    if not 1 <= API_PORT <= 65535:
        raise RuntimeError("API_PORT должен быть числом от 1 до 65535.")
    if not 0 <= DEFAULT_LIMIT <= 5000:
        raise RuntimeError("DEFAULT_LIMIT должен быть числом от 0 до 5000.")
