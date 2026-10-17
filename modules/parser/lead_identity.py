"""Conservative lead identity matching shared by search and SQLite storage."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from urllib.parse import urlsplit


def _contacts(lead: dict) -> dict:
    value = lead.get("contacts") or lead.get("c") or {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    return "".join(char for char in text if char.isalnum())


def normalize_phone(value: object, country: object = "") -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if str(country or "").upper() == "RU":
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        elif len(digits) == 10:
            digits = "7" + digits
    return digits if len(digits) >= 7 else ""


def _site_domain(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlsplit(raw).hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _identity_parts(lead: dict) -> dict[str, str]:
    contacts = _contacts(lead)
    name = normalize_text(lead.get("name"))
    country = str(lead.get("country") or "").upper()
    address = normalize_text(contacts.get("address"))
    if address:
        address = country + ":" + address
    site = lead.get("site_url") or lead.get("url") or contacts.get("site") or ""
    email = str(contacts.get("email") or lead.get("email") or "").strip().casefold()
    telegram = normalize_text(contacts.get("tg") or contacts.get("telegram"))
    return {
        "osm": str(lead.get("osm_key") or "").strip().casefold(),
        "name": name,
        "phone": normalize_phone(lead.get("phone"), country),
        "domain": _site_domain(site),
        "email": email,
        "telegram": telegram,
        "address": address,
    }


def identity_tokens(lead: dict) -> set[str]:
    parts = _identity_parts(lead)
    tokens = set()
    if parts["osm"]:
        tokens.add("osm:" + parts["osm"])
    if parts["phone"]:
        tokens.add("phone:" + parts["phone"])
    if parts["email"]:
        tokens.add("email:" + parts["email"])
    if parts["domain"] and parts["name"]:
        tokens.add("domain-name:" + parts["domain"] + ":" + parts["name"])
    if parts["name"] and parts["address"]:
        tokens.add("name-address:" + parts["name"] + ":" + parts["address"])
    if parts["telegram"] and parts["name"]:
        tokens.add("telegram-name:" + parts["telegram"] + ":" + parts["name"])
    return tokens


def same_business(left: dict, right: dict) -> bool:
    a = _identity_parts(left)
    b = _identity_parts(right)
    if a["osm"] and a["osm"] == b["osm"]:
        return True

    # Different known street addresses indicate separate branches, even when a
    # chain shares a phone number or a website.
    if a["address"] and b["address"] and a["address"] != b["address"]:
        return False

    same_name = bool(a["name"] and a["name"] == b["name"])
    same_domain = bool(a["domain"] and a["domain"] == b["domain"])
    same_email = bool(a["email"] and a["email"] == b["email"])
    same_phone = bool(a["phone"] and a["phone"] == b["phone"])
    same_telegram = bool(a["telegram"] and a["telegram"] == b["telegram"])

    if same_phone and (same_name or same_domain or same_email):
        return True
    if same_email and (same_name or same_domain):
        return True
    if same_domain and same_name:
        return True
    if same_telegram and same_name:
        return True
    return bool(same_name and a["address"] and a["address"] == b["address"])


class LeadIdentityIndex:
    """Small in-memory index for deduplicating leads without merging branches."""

    def __init__(self, leads=()):
        self._buckets: dict[str, list[dict]] = defaultdict(list)
        for lead in leads:
            self.add(lead)

    def find_duplicate(self, lead: dict, exclude: dict | None = None) -> dict | None:
        visited: set[int] = set()
        for token in identity_tokens(lead):
            for candidate in self._buckets.get(token, ()):
                marker = id(candidate)
                if candidate is exclude or marker in visited:
                    continue
                visited.add(marker)
                if same_business(lead, candidate):
                    return candidate
        return None

    def add(self, lead: dict) -> None:
        for token in identity_tokens(lead):
            bucket = self._buckets[token]
            if all(candidate is not lead for candidate in bucket):
                bucket.append(lead)



# Домены соцсетей, конструкторов и сервисов записи: у разных компаний один и тот же
# домен, поэтому сам по себе он не означает «та же компания».
SHARED_HOSTS = {
    "vk.com", "m.vk.com", "vk.ru", "instagram.com", "facebook.com", "fb.com", "t.me",
    "telegram.me", "wa.me", "whatsapp.com", "ok.ru", "youtube.com", "linktr.ee",
    "taplink.cc", "taplink.ws", "taplink.at", "yclients.com", "n.yclients.com", "dikidi.net",
    "dikidi.ru", "booksy.com", "fresha.com", "google.com", "goo.gl", "yandex.ru", "2gis.ru",
    "business.site", "maps.app.goo.gl", "tiktok.com", "mssg.me", "hipolink.me",
}


def _coord(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if -180 <= number <= 180 else None


def claim_tokens(lead: dict) -> set[str]:
    """Признаки, по которым бизнес закрепляется за одним пользователем навсегда.

    Совпадение любого признака = тот же бизнес (или тот же контакт), такой лид
    больше никому не выдаётся: телефон, email, домен, Telegram, Instagram, ВК,
    WhatsApp, ID в источнике, название+адрес и название+координаты (~100 м)."""
    parts = _identity_parts(lead)
    contacts = _contacts(lead)
    tokens = set()
    if parts["osm"]:
        tokens.add("osm:" + parts["osm"])
    if parts["phone"]:
        tokens.add("phone:" + parts["phone"])
    if parts["email"]:
        tokens.add("email:" + parts["email"])
    domain = parts["domain"]
    if domain and domain not in SHARED_HOSTS and not any(domain.endswith("." + host) for host in SHARED_HOSTS):
        tokens.add("domain:" + domain)
    if parts["telegram"]:
        tokens.add("tg:" + parts["telegram"])
    for key, prefix in (("ig", "ig:"), ("vk", "vk:"), ("vkg", "vk:")):
        value = normalize_text(contacts.get(key))
        if value:
            tokens.add(prefix + value)
    info = lead.get("info") if isinstance(lead.get("info"), dict) else {}
    for extra_phone in (info or {}).get("phones_e164") or []:
        normalized = normalize_phone(extra_phone)
        if normalized:
            tokens.add("phone:" + normalized)
    wa = normalize_phone(contacts.get("wa"))
    if wa:
        tokens.add("phone:" + wa)
    if parts["name"] and parts["address"]:
        tokens.add("name-address:" + parts["name"] + ":" + parts["address"])
    lat, lon = _coord(lead.get("lat")), _coord(lead.get("lon"))
    if lat is None and info:
        lat, lon = _coord(info.get("lat")), _coord(info.get("lon"))
    if parts["name"] and lat is not None and lon is not None:
        tokens.add(f"geo:{parts['name']}:{lat:.3f}:{lon:.3f}")
    return tokens
