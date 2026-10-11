"""Общие настройки тестов: временная папка для баз, тестовый токен и админ."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOKEN = "123456:TEST_TOKEN_for_tests_only"
ADMIN_ID = 111
os.environ.update({
    "BOT_TOKEN": TOKEN,
    "ADMIN_IDS": f"{ADMIN_ID}, @boss_admin",
    "DATA_DIR": tempfile.mkdtemp(prefix="cc-test-"),
    "PUBLIC_URL": "https://cc.example.com",
    "BOT_USERNAME": "CodeAndCash_bot",
    "CRYPTO_PAY_TOKEN": "1:crypto_test",
    "PAYMENT_PROVIDER_TOKEN": "provider:test",
})


def init_data(uid: int, username: str = "user", first_name: str = "Тест") -> str:
    user = json.dumps({"id": uid, "username": username, "first_name": first_name}, ensure_ascii=False)
    pairs = {"auth_date": str(int(time.time())), "query_id": "AAA", "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def headers(uid: int, **kw) -> dict:
    return {"X-Init-Data": init_data(uid, **kw)}
