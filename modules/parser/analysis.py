"""Анализ бизнеса: проверка сайта, классификация, приоритет 0–100 и объяснение.

Правило: ничего не придумываем. Если что-то не удалось проверить, так и пишем
(значение None = «не удалось проверить»), а лид с большим количеством
непроверяемых данных не попадает в выдачу."""

from __future__ import annotations

import asyncio
import html as html_lib
import re
import time
from urllib.parse import urljoin, urlsplit

import aiohttp

from . import contacts as cn

FREE_HOSTS = (
    "wixsite.com", "tilda.ws", "ucoz.ru", "narod.ru", "business.site",
    "wordpress.com", "blogspot.com", "jimdosite.com", "weebly.com",
    "nethouse.ru", "site123.me", "webnode.ru", "a5.ru", "taplink.cc", "taplink.ws",
    "mssg.me", "linktr.ee", "hipolink.me",
)

# Сервисы онлайн-записи и бронирования, которые встраивают на сайты.
BOOKING_WIDGETS = {
    "yclients.com": "YCLIENTS", "n.yclients.com": "YCLIENTS", "dikidi.net": "DIKIDI",
    "dikidi.ru": "DIKIDI", "booksy.com": "Booksy", "fresha.com": "Fresha",
    "altegio.com": "Altegio", "alteg.io": "Altegio", "sonline.su": "Sonline",
    "simplybook.me": "SimplyBook", "simplybook.it": "SimplyBook", "calendly.com": "Calendly",
    "arnica.pro": "Arnica", "easyweek.io": "EasyWeek", "bookon.ru": "Bookon",
    "medflex.ru": "MedFlex", "prodoctorov.ru": "ПроДокторов", "napopravku.ru": "НаПоправку",
    "znamenitosti.ru": "", "restoplace.ws": "Restoplace", "restoplace.cc": "Restoplace",
    "leclick.ru": "LeClick", "tablebooking.ru": "TableBooking", "quandoo.com": "Quandoo",
    "opentable.com": "OpenTable", "resy.com": "Resy", "zenchef.com": "Zenchef",
    "thefork.com": "TheFork", "remarked.ru": "ReMarked", "guestme.ru": "GuestMe",
    "booksy.net": "Booksy", "moment.pl": "Moment", "znanylekarz.pl": "ZnanyLekarz",
    "doctolib.de": "Doctolib", "treatwell.com": "Treatwell", "setmore.com": "Setmore",
    "square.site": "Square", "acuityscheduling.com": "Acuity", "mindbodyonline.com": "Mindbody",
}
BOOKING_WORDS = re.compile(
    r"онлайн[\s-]*запис|записаться\s+онлайн|запись\s+онлайн|онлайн[\s-]*бронир|"
    r"забронировать\s+стол|бронирование\s+стол|book\s+online|online\s+booking|book\s+now|"
    r"reserve\s+a\s+table|umów\s+wizytę|zarezerwuj|rezerwacja\s+online|termin\s+buchen|"
    r"онлайн[\s-]*жазыл",
    re.I,
)
RESERVATION_WORDS = re.compile(
    r"забронировать\s+стол|бронирование\s+стол|бронь\s+стол|reserve\s+a\s+table|rezerwacja\s+stolika",
    re.I,
)
CONTACT_LINK = re.compile(r"contact|kontakt|контакт|svyaz|связ", re.I)
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.I | re.S)
_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_FORM = re.compile(r"<form\b[^>]*>(.*?)</form\s*>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_SCRIPTS = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>", re.I | re.S)

NEED_LABELS = {
    "site_bot": "Нужен сайт и Telegram-бот",
    "site": "Нужен сайт",
    "broken": "Сайт не работает — нужен новый",
    "redesign": "Нужен редизайн сайта",
    "weak": "Слабый сайт — нужно улучшить",
    "bot": "Нормальный сайт, но нужен Telegram-бот",
}
SEVERE = ("не адаптирован под телефон", "не обновлялся", "почти пустая страница", "бесплатный поддомен", "конструктор-визитка")

CONTACT_WORDS = {
    "phone": "телефон", "tg": "Telegram", "wa": "WhatsApp", "vb": "Viber",
    "ig": "Instagram", "vk": "ВКонтакте", "fb": "Facebook", "email": "email",
}


def page_text(body: str) -> str:
    text = _SCRIPTS.sub(" ", body or "")
    text = _TAGS.sub(" ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def anchors(body: str) -> list[tuple[str, str]]:
    found = []
    for attrs, inner in _ANCHOR.findall(body or ""):
        match = _HREF.search(attrs)
        if not match:
            continue
        href = html_lib.unescape(next(group for group in match.groups() if group is not None).strip())
        found.append((href, page_text(inner)[:80]))
    return found


def has_contact_form(body: str) -> bool:
    """Форма заявки: есть поле телефона/email/текста. Поиск по сайту не считается."""
    for inner in _FORM.findall(body or ""):
        lowered = inner.lower()
        fields = re.findall(r"<(input|textarea|select)\b([^>]*)>", lowered)
        if not fields:
            continue
        useful = False
        for tag, attrs in fields:
            if tag == "textarea":
                useful = True
            kind = re.search(r'type\s*=\s*["\']?([a-z]+)', attrs)
            kind = kind.group(1) if kind else "text"
            name = re.search(r'name\s*=\s*["\']?([^"\'\s>]+)', attrs)
            name = name.group(1) if name else ""
            if kind in ("tel", "email"):
                useful = True
            if kind == "text" and re.search(r"phone|tel|name|имя|email|mail|fio|message", name):
                useful = True
            if kind == "search" or name in ("q", "s", "search", "query"):
                continue
        if useful:
            return True
    return False


def booking_service(body: str, links: list[tuple[str, str]]) -> str:
    lowered = (body or "").lower()
    for domain, title in BOOKING_WIDGETS.items():
        if domain in lowered:
            return title or domain
    text = page_text(body)
    if BOOKING_WORDS.search(text):
        return "онлайн-запись на сайте"
    for href, label in links:
        if BOOKING_WORDS.search(label):
            return "онлайн-запись на сайте"
    return ""


def telegram_links(links: list[tuple[str, str]]) -> tuple[str, str]:
    """Возвращает (аккаунт/канал, бот) из ссылок t.me на странице."""
    account = bot = ""
    for href, _label in links:
        lowered = href.lower()
        if "t.me/" not in lowered and "telegram.me/" not in lowered:
            continue
        name = cn.telegram(href)
        if not name:
            continue
        if is_bot_name(name):
            bot = bot or name
        else:
            account = account or name
    return account, bot


def is_bot_name(name: str) -> bool:
    """У Telegram-ботов имя пользователя обязательно заканчивается на «bot»."""
    return name.lstrip("@").lower().endswith("bot")


def copyright_year(text: str) -> int | None:
    years = [int(year) for year in re.findall(r"©\s*(?:\d{4}\s*[-–]\s*)?(20\d{2})", text)]
    years += [int(year) for year in re.findall(r"(?:copyright|\(c\))\s*(?:\d{4}\s*[-–]\s*)?(20\d{2})", text, re.I)]
    return max(years) if years else None


def contact_page_url(links: list[tuple[str, str]], page_url: str) -> str:
    base_host = (urlsplit(page_url).hostname or "").lower().removeprefix("www.")
    for href, label in links:
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if not (CONTACT_LINK.search(href) or CONTACT_LINK.search(label)):
            continue
        try:
            absolute = urljoin(page_url, href)
            host = (urlsplit(absolute).hostname or "").lower().removeprefix("www.")
        except ValueError:
            continue
        if host == base_host and absolute.split("#")[0] != page_url.split("#")[0]:
            return absolute
    return ""


def inspect_page(body: str, final_url: str, elapsed: float, last_modified: str = "") -> dict:
    """Проверки главной страницы, которые можно сделать без сети."""
    text = page_text(body)
    links = anchors(body)
    problems: list[str] = []
    https = final_url.startswith("https://")
    if not https:
        problems.append("нет HTTPS")
    mobile = bool(re.search(r"<meta[^>]+name\s*=\s*[\"']?viewport", body or "", re.I))
    if not mobile:
        problems.append("не адаптирован под телефон")
    speed = round(elapsed, 1)
    if elapsed > 3.0:
        problems.append(f"медленно загружается ({speed} с)")
    hostname = (urlsplit(final_url).hostname or "").lower()
    free_host = any(hostname == host or hostname.endswith("." + host) for host in FREE_HOSTS)
    if free_host:
        problems.append("бесплатный поддомен или конструктор-визитка")
    year = copyright_year(text)
    if year is None and last_modified:
        found = re.search(r"(20\d{2})", last_modified)
        year = int(found.group(1)) if found else None
    current_year = time.gmtime().tm_year
    actual = None if year is None else year > current_year - 3
    if actual is False:
        problems.append(f"не обновлялся с {year}")
    if len(text) < 400:
        problems.append("почти пустая страница")
    form = has_contact_form(body)
    booking = booking_service(body, links)
    reservation = bool(RESERVATION_WORDS.search(text))
    tg_account, tg_bot = telegram_links(links)
    has_phone_or_mail = bool(
        re.search(r'href\s*=\s*["\']?(tel:|mailto:)', body or "", re.I)
        or cn.email(text)
    )
    if not booking and not form:
        problems.append("нет онлайн-записи и формы заявки")
    elif not booking:
        problems.append("нет онлайн-записи")
    if not has_phone_or_mail:
        problems.append("на сайте не видно контактов")
    return {
        "https": https,
        "mobile": mobile,
        "speed": speed,
        "free_host": free_host,
        "year": year,
        "actual": actual,
        "form": form,
        "booking": booking,
        "reservation": reservation,
        "tg": tg_account,
        "tg_bot": tg_bot,
        "contacts_on_site": has_phone_or_mail,
        "problems": problems,
        "links": links,
    }


def classify(site: str, problems: list[str], has_tg_bot: bool) -> str:
    """Возвращает код потребности или "" (если бизнесу ничего не нужно)."""
    if site == "none":
        return "site" if has_tg_bot else "site_bot"
    if site == "broken":
        return "broken"
    if site == "weak":
        if any(problem.startswith(SEVERE) for problem in problems):
            return "redesign"
        return "weak"
    if site == "ok":
        return "" if has_tg_bot else "bot"
    return ""


def _join_ru(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " и " + items[-1]


def priority(lead: dict) -> tuple[int, str]:
    """Приоритет 0–100 и объяснение простыми словами на основе найденных данных."""
    site = lead.get("site", "none")
    need = lead.get("need", "")
    contacts = lead.get("contacts") or {}
    info = lead.get("info") or {}
    score = {
        "site_bot": 46, "site": 38, "broken": 42, "redesign": 34, "weak": 26, "bot": 20,
    }.get(need, 10)

    contact_points = 0
    present = []
    if lead.get("phone"):
        contact_points += 10
        present.append("phone")
    for key, points in (("tg", 8), ("wa", 6), ("ig", 5), ("vk", 4), ("vkg", 4), ("vb", 2), ("fb", 2), ("email", 3)):
        if contacts.get(key):
            contact_points += points
            word_key = "vk" if key == "vkg" else key
            if word_key not in present:
                present.append(word_key)
    score += min(contact_points, 24)

    tg_bot = info.get("tg_bot")
    if not tg_bot:
        score += 8
    booking = info.get("booking")
    if site in ("none", "broken") or (site in ("weak", "ok") and not booking):
        score += 6
    if info.get("hours"):
        score += 3
    rating, reviews = info.get("rating"), info.get("reviews")
    if rating and reviews and rating >= 4.0 and reviews >= 20:
        score += 5
    score -= 6 * int(info.get("unknown") or 0)
    score = max(0, min(100, score))

    if site == "none":
        parts = ["Сайт отсутствует"]
    elif site == "broken":
        reason = (lead.get("reasons") or ["не открывается"])[0]
        parts = [f"Сайт не работает ({reason})"]
    elif site == "weak":
        reasons = [reason for reason in (lead.get("reasons") or []) if not reason.startswith("нет онлайн-записи")]
        parts = ["Сайт слабый: " + ", ".join((reasons or lead.get("reasons") or [])[:2])]
    else:
        parts = ["Сайт нормальный"]
    if present:
        parts.append("есть " + _join_ru([CONTACT_WORDS[key] for key in present]))
    if tg_bot:
        parts.append(f"Telegram-бот уже есть ({tg_bot})")
    else:
        parts.append("Telegram-бот не найден")
    if site in ("weak", "ok"):
        parts.append(f"онлайн-запись: {booking}" if booking else "онлайн-записи нет")
    if rating and reviews:
        parts.append(f"рейтинг {rating} ({reviews} отзывов)")
    return score, ", ".join(parts) + "."


class TelegramChecker:
    """Проверяет, что публичная ссылка t.me действительно открывает аккаунт, канал или бота.

    Возвращает True (существует), False (такой страницы нет) или None (не удалось проверить)."""

    def __init__(self, session: aiohttp.ClientSession, concurrency: int = 4):
        self.session = session
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache: dict[str, bool | None] = {}

    async def exists(self, name: str) -> bool | None:
        key = name.lstrip("@").lower()
        if not key:
            return False
        if key in self.cache:
            return self.cache[key]
        async with self.semaphore:
            try:
                async with self.session.get(
                    f"https://t.me/{key}",
                    timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": "Mozilla/5.0 (compatible; ParserCC/2.0)"},
                ) as response:
                    if response.status != 200:
                        result = None
                    else:
                        body = (await response.content.read(60_000)).decode("utf-8", "ignore")
                        result = "tgme_page_title" in body
            except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
                result = None
        self.cache[key] = result
        return result


class SocialChecker:
    """Проверяет, что страница ВКонтакте или Instagram ещё существует.

    Данные карт бывают старыми: сообщество удалили или переименовали. Такие
    ссылки не показываем. True — страница есть, False — её нет, None — не удалось
    проверить (например, сайт попросил войти); тогда ссылку оставляем."""

    URLS = {"vk": "https://vk.com/{}", "ig": "https://www.instagram.com/{}/"}
    DEAD_MARKERS = (
        "страница удалена", "страница не найдена", "page not found", "this page has either been deleted",
        "сообщество заблокировано", "страница заблокирована", "sorry, this page isn't available",
        "эта страница недоступна", "httperrorpage",
    )

    def __init__(self, session: aiohttp.ClientSession, concurrency: int = 4):
        self.session = session
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache: dict[tuple[str, str], bool | None] = {}

    async def exists(self, kind: str, name: str) -> bool | None:
        key = (kind, name.lstrip("@").lower())
        if not key[1] or kind not in self.URLS:
            return None
        if key in self.cache:
            return self.cache[key]
        result: bool | None = None
        async with self.semaphore:
            try:
                async with self.session.get(
                    self.URLS[kind].format(key[1]),
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                        "Accept-Language": "ru,en;q=0.8",
                    },
                ) as response:
                    if response.status in (404, 410):
                        result = False
                    elif response.status == 200:
                        body = (await response.content.read(200_000)).decode("utf-8", "ignore").lower()
                        if any(marker in body for marker in self.DEAD_MARKERS):
                            result = False
                        elif kind == "ig":
                            result = True if f"@{key[1]}" in body or f'"username":"{key[1]}"' in body else None
                        else:
                            result = True if "<title>" in body else None
            except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
                result = None
        self.cache[key] = result
        return result
