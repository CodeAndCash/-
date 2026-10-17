"""Оплата: крипта через @CryptoBot (Crypto Pay API), карта и звёзды — счётом Telegram."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import aiohttp
from aiogram.types import LabeledPrice

from . import config, db
from .tg import bot

log = logging.getLogger("cc.payments")


def methods() -> list[str]:
    """Какие способы оплаты включены (в таком порядке показываются кнопки)."""
    out = []
    if config.PAYMENT_PROVIDER_TOKEN or config.TRIBUTE_API_KEY:
        out.append("card")
    if config.CRYPTO_PAY_TOKEN:
        out.append("crypto")
    if config.STARS_ENABLED:
        out.append("stars")
    return out


# ---------- Crypto Pay ----------

def _crypto_base() -> str:
    host = "testnet-pay.crypt.bot" if config.CRYPTO_PAY_TESTNET else "pay.crypt.bot"
    return f"https://{host}/api"


async def crypto_call(method: str, payload: dict | None = None) -> dict:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{_crypto_base()}/{method}",
            json=payload or {},
            headers={"Crypto-Pay-API-Token": config.CRYPTO_PAY_TOKEN},
        ) as response:
            data = await response.json(content_type=None)
    if not data.get("ok"):
        raise RuntimeError(f"Crypto Pay: {data.get('error')}")
    return data["result"]


async def crypto_invoice(payment: dict, title: str) -> tuple[str, str]:
    """Счёт в рублях — человек платит любой криптой из списка по курсу CryptoBot."""
    result = await crypto_call("createInvoice", {
        "currency_type": "fiat",
        "fiat": "RUB",
        "amount": f"{payment['amount']:.2f}",
        "accepted_assets": config.CRYPTO_ASSETS,
        "description": f"C&C Family · {title}"[:1024],
        "payload": f"cc:{payment['id']}",
        "paid_btn_name": "openBot",
        "paid_btn_url": f"https://t.me/{config.BOT_USERNAME}",
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    })
    url = result.get("mini_app_invoice_url") or result.get("bot_invoice_url") or result.get("pay_url") or ""
    return str(result["invoice_id"]), url


async def crypto_paid_ids(invoice_ids: list[str]) -> dict[str, str]:
    """Статусы счетов: {invoice_id: status}."""
    if not invoice_ids:
        return {}
    result = await crypto_call("getInvoices", {"invoice_ids": ",".join(invoice_ids), "count": 1000})
    items = result.get("items", []) if isinstance(result, dict) else result
    return {str(item["invoice_id"]): item.get("status", "") for item in items}


def crypto_signature_ok(body: bytes, signature: str) -> bool:
    if not config.CRYPTO_PAY_TOKEN or not signature:
        return False
    secret = hashlib.sha256(config.CRYPTO_PAY_TOKEN.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_crypto_update(body: bytes) -> tuple[str, str] | None:
    """(invoice_id, status) из уведомления Crypto Pay."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if data.get("update_type") != "invoice_paid":
        return None
    invoice = data.get("payload") or {}
    return str(invoice.get("invoice_id", "")), invoice.get("status", "")


# ---------- Tribute: карта ----------

def tribute_signature_ok(body: bytes, signature: str) -> bool:
    """trbt-signature — HMAC-SHA256 тела запроса ключом API (принимаем hex и base64)."""
    if not config.TRIBUTE_API_KEY or not signature:
        return False
    digest = hmac.new(config.TRIBUTE_API_KEY.encode(), body, hashlib.sha256).digest()
    signature = signature.strip()
    import base64
    return hmac.compare_digest(digest.hex(), signature.lower()) or hmac.compare_digest(
        base64.b64encode(digest).decode(), signature)


def parse_tribute(body: bytes) -> dict | None:
    """Событие Tribute в удобном виде: kind, uid, product, amount (₽), until, key — или None."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    name = str(data.get("name") or "")
    name = "".join("_" + c.lower() if c.isupper() else c for c in name)  # newDigitalProduct → new_digital_product
    p = data.get("payload") or {}
    uid = p.get("telegram_user_id")
    if not isinstance(uid, int):
        return None
    amount = float(p.get("amount") or p.get("price") or 0) / 100
    if name == "new_digital_product":
        return {"kind": "product", "uid": uid, "product": int(p.get("product_id") or 0), "amount": amount,
                "currency": p.get("currency") or "rub", "key": f"tribute:purchase:{p.get('purchase_id')}",
                "username": p.get("telegram_username") or ""}
    if name in ("new_subscription", "renewed_subscription"):
        import datetime as dt
        try:
            until = int(dt.datetime.fromisoformat(str(p.get("expires_at")).replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
        return {"kind": "subscription", "uid": uid, "product": int(p.get("subscription_id") or 0), "amount": amount,
                "currency": p.get("currency") or "rub", "until": until,
                "key": f"tribute:sub:{p.get('subscription_id')}:{p.get('expires_at')}",
                "username": p.get("telegram_username") or ""}
    if name == "cancelled_subscription":
        return {"kind": "cancelled", "uid": uid, "product": int(p.get("subscription_id") or 0), "amount": 0,
                "currency": "", "key": "", "username": p.get("telegram_username") or ""}
    return {"kind": "other", "uid": uid, "name": name, "product": 0, "amount": 0, "currency": "", "key": "",
            "username": ""}


# ---------- Счёт Telegram: карта (через провайдера) и звёзды ----------

async def telegram_invoice_link(payment: dict, title: str, description: str) -> str:
    stars = payment["method"] == "stars"
    amount = int(round(payment["amount"])) if stars else int(round(payment["amount"] * 100))
    extra: dict = {}
    if not stars and config.CARD_RECEIPT:
        # Чек по 54-ФЗ для ЮKassa: Telegram спросит почту и передаст провайдеру.
        extra = {
            "need_email": True,
            "send_email_to_provider": True,
            "provider_data": json.dumps({"receipt": {"items": [{
                "description": title[:128], "quantity": "1.00",
                "amount": {"value": f"{payment['amount']:.2f}", "currency": config.CARD_CURRENCY},
                "vat_code": config.CARD_VAT_CODE, "payment_mode": "full_payment", "payment_subject": "service",
            }]}}, ensure_ascii=False),
        }
    return await bot.create_invoice_link(
        title=title[:32],
        description=description[:255],
        payload=f"cc:{payment['id']}",
        provider_token="" if stars else config.PAYMENT_PROVIDER_TOKEN,
        currency="XTR" if stars else config.CARD_CURRENCY,
        prices=[LabeledPrice(label=title[:32], amount=amount)],
        **extra,
    )


def expected_total(payment: dict) -> int:
    if payment["method"] == "stars":
        return int(round(payment["amount"]))
    return int(round(payment["amount"] * 100))


async def payment_from_payload(payload: str) -> dict | None:
    if not payload.startswith("cc:"):
        return None
    raw = payload[3:]
    return await db.get_payment(int(raw)) if raw.isdigit() else None
