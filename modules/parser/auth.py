import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from .config import BOT_TOKEN

# Telegram не обновляет initData, пока мини-апп открыт, поэтому даём сутки.
# Защищает подпись HMAC, а не срок.
MAX_AGE_SECONDS = 24 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 60


def verify_init_data(init_data: str) -> dict | None:
    """Validate Telegram Web App initData and return its signed user object."""
    if not init_data:
        return None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={pairs[key]}" for key in sorted(pairs)
        )
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        auth_date = int(pairs.get("auth_date", "0"))
        age = time.time() - auth_date
        if auth_date <= 0 or age > MAX_AGE_SECONDS or age < -MAX_FUTURE_SKEW_SECONDS:
            return None

        user = json.loads(pairs["user"])
        return user if isinstance(user, dict) and isinstance(user.get("id"), int) else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
