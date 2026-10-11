"""Приводит контакты к одному проверенному виду, чтобы ссылки открывались."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, unquote, urlsplit

import phonenumbers

CIS_MAPS = {"RU", "BY", "KZ", "UZ", "KG", "TJ", "AM", "AZ", "MD"}

_TG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")
_TG_RESERVED = {
    "share", "joinchat", "addstickers", "addemoji", "proxy", "socks", "iv",
    "setlanguage", "login", "confirmphone", "bg", "addtheme", "boost", "contact",
    "http", "https", "www",
}
_VK_RESERVED = {
    "http", "https", "www", "share.php", "away.php", "login", "feed", "im",
    "search", "video", "photo", "app", "apps", "widget_community.php", "js",
    "images", "doc", "wall", "write", "settings", "groups", "friends", "music",
}
_IG_RESERVED = {
    "http", "https", "www", "p", "reel", "reels", "stories", "explore",
    "accounts", "direct", "tv", "about", "legal", "developer", "web",
}
_FB_RESERVED = {"sharer", "sharer.php", "share", "dialog", "plugins", "tr", "login", "home.php"}
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,24}", re.I)
_EMAIL_JUNK_DOMAINS = (
    "example.com", "example.org", "domain.com", "sentry.io", "sentry-next.wixpress.com",
    "wixpress.com", "email.com", "yoursite.com", "site.com", "mysite.com",
)
_IMAGE_TAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|bmp)$", re.I)


def _clean(raw: object) -> str:
    text = unquote(str(raw or "")).strip().strip("<>\"'`«» \t\r\n")
    return text.split(";", 1)[0].strip()


def _host_path(raw: str) -> tuple[str, str, str]:
    """Возвращает хост, путь и query для строки со ссылкой или без схемы."""
    value = raw.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        value = "https://" + value.lstrip("/")
    try:
        parts = urlsplit(value)
    except ValueError:
        return "", "", ""
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host, unquote(parts.path or ""), parts.query or ""


def _looks_like_url(value: str) -> bool:
    return bool(re.search(r"^[a-z]+://|^(www\.)?[a-z0-9-]+\.[a-z]{2,}/", value, re.I))


def phone(raw: object, country: str = "") -> tuple[str, str]:
    """Возвращает (E.164, красивый вид) для первого настоящего номера или ("", "")."""
    text = str(raw or "")
    if not text.strip():
        return "", ""
    region = (country or "").upper() or None
    text = re.sub(r"(?<=\d)\s*(?=\+\d)", ";", text)
    for part in re.split(r"[;,/|]|\s+(?:или|or)\s+", text):
        part = part.strip()
        digits = re.sub(r"\D", "", part)
        if len(digits) < 7 or len(digits) > 15:
            continue
        try:
            number = phonenumbers.parse(part, region)
        except phonenumbers.NumberParseException:
            continue
        if not phonenumbers.is_valid_number(number):
            continue
        e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        pretty = phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        return e164, pretty
    return "", ""


def phone_digits(raw: object, country: str = "") -> str:
    e164, _ = phone(raw, country)
    return e164.lstrip("+")


def telegram(raw: object) -> str:
    value = _clean(raw)
    if not value:
        return ""
    if _looks_like_url(value) or "t.me" in value.lower() or "telegram." in value.lower():
        host, path, _ = _host_path(value)
        if host not in {"t.me", "telegram.me", "telegram.dog"}:
            return ""
        segments = [segment for segment in path.split("/") if segment]
        if segments and segments[0] == "s":
            segments = segments[1:]
        name = segments[0].lstrip("@") if segments else ""
    else:
        name = value.lstrip("@").strip()
    if name.startswith("+") or name.lower() in _TG_RESERVED:
        return ""
    if not _TG_NAME.fullmatch(name):
        return ""
    return "@" + name


def whatsapp(raw: object, country: str = "") -> str:
    value = _clean(raw)
    if not value:
        return ""
    lowered = value.lower()
    if "wa.me" in lowered or "whatsapp.com" in lowered:
        host, path, query = _host_path(value)
        if host in {"wa.me"}:
            value = path.strip("/").split("/", 1)[0]
        elif host.endswith("whatsapp.com"):
            value = parse_qs(query).get("phone", [""])[0]
        else:
            return ""
        if value and not value.startswith("+"):
            value = "+" + re.sub(r"\D", "", value)
    return phone_digits(value, country)


def viber(raw: object, country: str = "") -> str:
    value = _clean(raw)
    if value.lower().startswith("viber://"):
        value = parse_qs(urlsplit(value).query).get("number", [""])[0] or value
    return phone_digits(value, country)


def vk(raw: object) -> str:
    """Возвращает короткий адрес страницы ВК (например club123 или barber_city)."""
    value = _clean(raw)
    if not value:
        return ""
    if _looks_like_url(value) or re.search(r"(^|\.)vk\.(com|ru)\b", value, re.I):
        host, path, _ = _host_path(value)
        if host not in {"vk.com", "m.vk.com", "vk.ru", "m.vk.ru", "new.vk.com"}:
            return ""
        segments = [segment for segment in path.split("/") if segment]
        name = segments[0] if segments else ""
    else:
        name = value.lstrip("@")
    name = name.strip(".")
    if name.lower() in _VK_RESERVED:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.]{2,64}", name):
        return ""
    if re.fullmatch(r"\d+", name):
        return ""
    return name


def instagram(raw: object) -> str:
    value = _clean(raw)
    if not value:
        return ""
    if _looks_like_url(value) or "instagram.com" in value.lower() or "instagr.am" in value.lower():
        host, path, _ = _host_path(value)
        if host not in {"instagram.com", "m.instagram.com", "instagr.am"}:
            return ""
        segments = [segment for segment in path.split("/") if segment]
        name = segments[0] if segments else ""
    else:
        name = value
    name = name.lstrip("@")
    if name.lower() in _IG_RESERVED:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", name):
        return ""
    if name.startswith(".") or name.endswith(".") or ".." in name:
        return ""
    return name


def facebook(raw: object) -> str:
    value = _clean(raw)
    if not value:
        return ""
    if _looks_like_url(value) or "facebook.com" in value.lower() or "fb.com" in value.lower():
        host, path, query = _host_path(value)
        if host not in {"facebook.com", "m.facebook.com", "fb.com", "business.facebook.com"}:
            return ""
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return ""
        if segments[0] == "profile.php":
            page_id = parse_qs(query).get("id", [""])[0]
            return f"https://www.facebook.com/profile.php?id={page_id}" if page_id.isdigit() else ""
        if segments[0] in ("pages", "people") and len(segments) >= 3:
            tail = "/".join(segments[:3])
            return "https://www.facebook.com/" + quote(tail, safe="/-_.")
        name = segments[0]
    else:
        name = value.lstrip("@")
    if name.lower() in _FB_RESERVED or not re.fullmatch(r"[A-Za-z0-9.\-]{2,80}", name):
        return ""
    return "https://www.facebook.com/" + name


def email(raw: object) -> str:
    match = _EMAIL.search(str(raw or ""))
    if not match:
        return ""
    address = match.group(0).strip(".").lower()
    domain = address.rsplit("@", 1)[-1]
    if _IMAGE_TAIL.search(address) or any(
        domain == junk or domain.endswith("." + junk) for junk in _EMAIL_JUNK_DOMAINS
    ):
        return ""
    return address


def map_link(lat: object, lon: object, name: str = "", country: str = "") -> str:
    """Ссылка, которая открывает на карте саму организацию: поиск по названию
    рядом с её точкой. Так открывается карточка бизнеса с фото, отзывами и
    часами работы, а не просто метка на карте."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return ""
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return ""
    title = re.sub(r"\s+", " ", str(name or "")).strip()[:120]
    if (country or "").upper() in CIS_MAPS:
        link = f"https://yandex.ru/maps/?ll={lon_f:.6f},{lat_f:.6f}&z=18"
        if title:
            link += "&text=" + quote(title)
        else:
            link += f"&pt={lon_f:.6f},{lat_f:.6f}"
        return link
    if title:
        return f"https://www.google.com/maps/search/{quote(title)}/@{lat_f:.6f},{lon_f:.6f},18z"
    return f"https://www.google.com/maps/search/?api=1&query={lat_f:.6f}%2C{lon_f:.6f}"


def phones(raw: object, country: str = "", limit: int = 5) -> list[tuple[str, str]]:
    """Все настоящие номера из строки (часто их пишут через «;»), без повторов."""
    text = str(raw or "")
    text = re.sub(r"(?<=\d)\s*(?=\+\d)", ";", text)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for part in re.split(r"[;,/|]|\s+(?:или|or)\s+", text):
        e164, pretty = phone(part, country)
        if e164 and e164 not in seen:
            seen.add(e164)
            found.append((e164, pretty))
        if len(found) >= limit:
            break
    return found


SOCIAL_KEYS = ("tg", "wa", "vb", "vk", "vkg", "ig", "fb")


def clean_contacts(raw: dict | None, country: str = "") -> dict:
    """Перепроверяет уже сохранённые контакты и выкидывает битые значения."""
    source = dict(raw or {})
    result: dict[str, str] = {}
    tg = telegram(source.get("tg", ""))
    if tg:
        result["tg"] = tg
    wa = whatsapp(source.get("wa", ""), country)
    if wa:
        result["wa"] = wa
    vb = viber(source.get("vb", ""), country)
    if vb:
        result["vb"] = vb
    for key in ("vk", "vkg"):
        value = vk(source.get(key, ""))
        if value:
            result["vkg" if value.startswith(("club", "public", "event")) else "vk"] = value
            break
    ig = instagram(source.get("ig", ""))
    if ig:
        result["ig"] = ig
    fb = facebook(source.get("fb", ""))
    if fb:
        result["fb"] = fb
    mail = email(source.get("email", ""))
    if mail:
        result["email"] = mail
    for key in ("address", "site", "map"):
        value = str(source.get(key) or "").strip()
        if value:
            result[key] = value
    return result


def has_reachable_contact(phone_value: str, contacts: dict) -> bool:
    return bool(phone_value) or any(contacts.get(key) for key in SOCIAL_KEYS)
