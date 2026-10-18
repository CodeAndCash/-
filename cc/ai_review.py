"""AI-оценка присланных работ: нейронка смотрит скриншоты и сам сайт по ссылке,
ставит оценку от 1 до 5 и коротко пишет, чего не хватает и где могут быть ошибки.

Подключение — переменные Railway:
  ANTHROPIC_API_KEY — ключ Claude (console.anthropic.com), или
  OPENROUTER_API_KEY — ключ OpenRouter (openrouter.ai), если Claude напрямую оплатить неудобно.
  AI_MODEL — модель (необязательно). По умолчанию claude-sonnet-5-5.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time

from html.parser import HTMLParser

import aiohttp

from . import config

log = logging.getLogger("cc.ai")

MAX_IMAGES = 6
MAX_SIDE = 1568
SITE_BYTES = 1_500_000

SYSTEM = """Ты — строгий и честный арт-директор веб-студии. Тебе присылают сайты учеников, которые учатся делать сайты для малого бизнеса с помощью нейросетей и продавать их. Твоя задача — оценить работу так, как оценил бы требовательный заказчик, и коротко сказать, что исправить.

Шкала (ставь целое число):
5 — отлично. Можно сдавать клиенту как есть: аккуратная современная вёрстка без поломок, понятное предложение на первом экране, заметная кнопка действия, контакты, нормальная мобильная версия, живые тексты без заглушек.
4 — хорошо. В целом готово, но есть 2–4 заметные недоработки.
3 — средне. Работает, но выглядит как шаблон или черновик: слабый первый экран, общие тексты, мелкие поломки, не хватает важных блоков.
2 — плохо. Вёрстка разъезжается, непонятно, что предлагают и куда нажать, нет контактов, тексты-заглушки (lorem ipsum, «Ваш текст»), явные ошибки.
1 — не оценить: пусто, не сайт, нечитаемые скриншоты или не по теме.

Правила:
- Не завышай. Большинство первых работ — это 3. Пятёрку ставь редко и только за действительно сильную работу.
- Оценивай только то, что видно на скриншотах и в коде страницы. Если что-то проверить нельзя (например, нет вида с телефона), так и скажи, а не придумывай.
- Пиши по-русски, просто, на «ты», без воды и без комплиментов ради комплиментов. Каждый пункт — одно короткое предложение.
- Ищи конкретику: опечатки, обрезанный текст, налезающие элементы, мелкий шрифт, низкий контраст, нерабочие или пустые ссылки, нет title/description, нет viewport, картинки без alt, нет формы или кнопки связи, нет телефона/мессенджера, нет цен, нет отзывов, http вместо https.

Ответь строго JSON без пояснений вокруг:
{"score": 1-5, "verdict": "1–2 предложения: общее впечатление и главная проблема",
 "good": ["что сделано хорошо", ...до 3],
 "missing": ["чего не хватает на сайте", ...до 5],
 "errors": ["где ошибка или может быть ошибка, с указанием места", ...до 5],
 "advice": ["что сделать в первую очередь", ...до 3]}"""


def enabled() -> bool:
    return bool(config.ANTHROPIC_API_KEY or config.OPENROUTER_API_KEY)


def provider() -> str:
    return "anthropic" if config.ANTHROPIC_API_KEY else "openrouter" if config.OPENROUTER_API_KEY else ""


def model() -> str:
    if config.AI_MODEL:
        return config.AI_MODEL
    return "claude-sonnet-5-5" if provider() == "anthropic" else "anthropic/claude-sonnet-5.5"


# ---------- Подготовка материалов ----------

def prepare_image(data: bytes) -> tuple[str, str] | None:
    """Уменьшаем скриншот до разумного размера и переводим в JPEG. Возвращает (mime, base64)."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img.load()
        if img.mode not in ("RGB", "L"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = bg
        img = img.convert("RGB")
        # Очень длинные скриншоты страницы режем на верхнюю часть: нейронке важнее первый экран и пара блоков.
        w, h = img.size
        if h > w * 4:
            img = img.crop((0, 0, w, w * 4))
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=82, optimize=True)
        return "image/jpeg", base64.b64encode(out.getvalue()).decode()
    except Exception as exc:  # битая картинка — просто пропускаем
        log.info("AI: картинку не прочитать: %s", exc)
        return None


def _clean(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


async def _public_host(url: str) -> bool:
    """Не ходим по ссылкам во внутреннюю сеть сервера (localhost, 10.x и т.п.)."""
    import ipaddress
    import socket
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    if not host:
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return True  # не резолвится — пусть запрос сам упадёт и это попадёт в разбор как ошибка
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


class _Page(HTMLParser):
    """Собирает со страницы то, что нужно нейронке: заголовки, тексты, ссылки, мета-теги."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.lang, self.favicon, self.forms = "", "", False, 0
        self.meta: dict[str, str] = {}
        self.heads: list[list[str]] = []
        self.img_alts: list[str] = []
        self.links: list[str] = []
        self.buttons: list[str] = []
        self.text: list[str] = []
        self._skip = 0
        self._in_title = False
        self._head: list[str] | None = None
        self._button: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        elif tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and "icon" in a.get("rel", "").lower():
            self.favicon = True
        elif tag in ("h1", "h2", "h3"):
            self._head = [tag, ""]
            self.heads.append(self._head)
        elif tag == "img":
            self.img_alts.append(a.get("alt", ""))
        elif tag == "a":
            self.links.append(a.get("href", "").strip())
            if re.search(r"btn|button", a.get("class", ""), re.I):
                self._button = []
        elif tag == "button":
            self._button = []
        elif tag == "form":
            self.forms += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3"):
            self._head = None
        elif tag in ("a", "button") and self._button is not None:
            self.buttons.append(" ".join(self._button))
            self._button = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        self.text.append(data)
        if self._head is not None:
            self._head[1] += data
        if self._button is not None:
            self._button.append(data)


async def fetch_site(url: str) -> str:
    """Скачивает страницу и собирает короткую сводку для нейронки: заголовки, тексты, ссылки, технические мелочи."""
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    if not await _public_host(url):
        return f"Ссылка {url} ведёт не на публичный сайт — её не проверить."
    started = time.monotonic()
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                                 "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True, ssl=False) as resp:
                status = resp.status
                final = str(resp.url)
                raw = await resp.content.read(SITE_BYTES)
    except Exception as exc:
        return f"Сайт по ссылке {url} не открылся: {exc.__class__.__name__}. Это тоже стоит учесть как ошибку."
    took = time.monotonic() - started
    page = _Page()
    try:
        page.feed(raw.decode("utf-8", errors="replace"))
        page.close()
    except Exception:
        return f"Ссылка {final} ответила кодом {status}, но страницу не удалось разобрать."
    meta = page.meta
    title = _clean(page.title, 200)
    heads = [f"{tag}: {_clean(text, 140)}" for tag, text in page.heads if text.strip()][:30]
    no_alt = sum(1 for alt in page.img_alts if not alt.strip())
    links = page.links
    empty_links = sum(1 for h in links if h in ("", "#", "javascript:void(0)", "javascript:;"))
    contacts = sorted({h.split(":")[0] for h in links if h.startswith(("tel:", "mailto:"))} |
                      {"telegram" for h in links if "t.me/" in h} | {"whatsapp" for h in links if "wa.me" in h or "whatsapp" in h})
    buttons = [_clean(b, 40) for b in page.buttons if b.strip()][:15]
    body = _clean(" ".join(page.text), 5000)
    lorem = bool(re.search(r"lorem ipsum|ваш текст|текст текст|placeholder|заголовок раздела", body, re.I))
    lines = [
        f"Ссылка: {final} (ответ {status}, загрузка {took:.1f} с, {len(raw) // 1024} КБ HTML{', обрезано' if len(raw) >= SITE_BYTES else ''})",
        f"HTTPS: {'да' if final.startswith('https://') else 'нет'}",
        f"title: {title or 'НЕТ'}",
        f"meta description: {_clean(meta.get('description', ''), 200) or 'НЕТ'}",
        f"viewport для телефона: {'есть' if meta.get('viewport') else 'НЕТ'}",
        f"lang: {page.lang or 'не указан'}; favicon: {'есть' if page.favicon else 'нет'}; "
        f"og:image: {'есть' if meta.get('og:image') else 'нет'}",
        f"Картинок: {len(page.img_alts)}, без alt: {no_alt}. Ссылок: {len(links)}, пустых (#): {empty_links}. "
        f"Форм: {page.forms}.",
        f"Контакты-ссылки: {', '.join(contacts) or 'не найдены'}",
        f"Кнопки: {', '.join(b for b in buttons if b) or 'не найдены'}",
        f"Похоже на текст-заглушку: {'да' if lorem else 'нет'}",
        "Заголовки:\n" + ("\n".join(heads) or "нет"),
        "Текст страницы (начало):\n" + body,
    ]
    return "\n".join(lines)


# ---------- Запрос к нейронке ----------

def _user_text(url: str, comment: str, site: str, n_images: int, n_videos: int) -> str:
    parts = [f"Скриншотов приложено: {n_images}."]
    if n_videos:
        parts.append(f"Ещё прислали видео ({n_videos}) — видео ты не видишь, оценивай по скриншотам и коду.")
    if comment:
        parts.append(f"Комментарий ученика (что важно оценить): {comment}")
    if site:
        parts.append("Данные со страницы сайта:\n" + site)
    elif url:
        parts.append(f"Ссылка: {url}")
    else:
        parts.append("Ссылки на сайт нет — оценивай только по скриншотам.")
    parts.append("Оцени работу по шкале и ответь JSON.")
    return "\n\n".join(parts)


async def _post(url: str, headers: dict, payload: dict) -> dict:
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                err = data.get("error") if isinstance(data, dict) else data
                if isinstance(err, dict):
                    err = err.get("message") or err
                raise RuntimeError(f"{resp.status}: {err}")
            return data


async def ask(images: list[tuple[str, str]], text: str) -> str:
    if provider() == "anthropic":
        content = [{"type": "image", "source": {"type": "base64", "media_type": m, "data": d}} for m, d in images]
        content.append({"type": "text", "text": text})
        data = await _post("https://api.anthropic.com/v1/messages",
                           {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                            "content-type": "application/json"},
                           {"model": model(), "max_tokens": 1500, "temperature": 0.2, "system": SYSTEM,
                            "messages": [{"role": "user", "content": content}]})
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    content = [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{d}"}} for m, d in images]
    content.append({"type": "text", "text": text})
    base = (config.AI_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/")
    data = await _post(f"{base}/chat/completions",
                       {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "Content-Type": "application/json",
                        "HTTP-Referer": config.PUBLIC_URL or "https://t.me", "X-Title": "C&C Family"},
                       {"model": model(), "max_tokens": 1500, "temperature": 0.2,
                        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]})
    return data["choices"][0]["message"]["content"] or ""


def parse(answer: str) -> dict:
    """Достаём JSON из ответа и приводим к аккуратному виду."""
    match = re.search(r"\{.*\}", answer or "", re.S)
    if not match:
        raise ValueError("нейронка ответила не JSON")
    data = json.loads(match.group(0))
    score = int(round(float(data.get("score", 0))))
    if not 1 <= score <= 5:
        raise ValueError(f"странная оценка: {data.get('score')}")

    def items(key: str, limit: int) -> list[str]:
        value = data.get(key) or []
        if isinstance(value, str):
            value = [value]
        return [_clean(str(v), 300) for v in value if str(v).strip()][:limit]

    return {"score": score, "verdict": _clean(str(data.get("verdict") or ""), 500),
            "good": items("good", 3), "missing": items("missing", 5), "errors": items("errors", 5),
            "advice": items("advice", 3)}


async def review(url: str, comment: str, files: list[tuple[str, bytes]]) -> dict:
    """files — [(mime, bytes)]. Возвращает разобранный ответ нейронки."""
    images = []
    for mime, data in files:
        if mime.startswith("image/") and len(images) < MAX_IMAGES:
            prepared = await asyncio.to_thread(prepare_image, data)
            if prepared:
                images.append(prepared)
    videos = sum(1 for mime, _ in files if mime.startswith("video/"))
    site = await fetch_site(url) if url else ""
    if not images and not site:
        return {"score": 1, "verdict": "Нечего оценить: нет ни читаемых скриншотов, ни ссылки на сайт. "
                                       "Пришли скриншоты сайта или ссылку.", "good": [], "missing": [], "errors": [],
                "advice": ["Сделай 3–5 скриншотов: первый экран, пару блоков и вид с телефона"]}
    answer = await ask(images, _user_text(url, comment, site, len(images), videos))
    try:
        return parse(answer)
    except (ValueError, TypeError) as first:
        log.info("AI: переспрашиваю, %s", first)
        answer = await ask(images, _user_text(url, comment, site, len(images), videos) +
                           "\n\nВажно: ответ — только JSON-объект, без текста вокруг.")
        return parse(answer)


def format_text(result: dict) -> str:
    """Человеческий текст для сообщения в боте (HTML)."""
    import html

    def block(title: str, rows: list[str]) -> str:
        return f"\n\n<b>{title}</b>\n" + "\n".join(f"• {html.escape(r)}" for r in rows) if rows else ""

    stars = "★" * result["score"] + "☆" * (5 - result["score"])
    return (f"<b>Оценка нейронки: {result['score']}/5</b> {stars}\n{html.escape(result['verdict'])}"
            + block("Что хорошо", result.get("good", []))
            + block("Чего не хватает", result.get("missing", []))
            + block("Где может быть ошибка", result.get("errors", []))
            + block("Что сделать первым", result.get("advice", [])))
