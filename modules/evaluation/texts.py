"""Тексты бота, которые админы меняют в мини-аппе («Сообщения»). HTML-разметка Telegram.

Подстановки в фигурных скобках заменяются при отправке; неизвестные остаются как есть."""
from __future__ import annotations

import html
import re

GROUPS = ("Старт", "Заявка", "Оплата")

DEFAULTS: dict[str, dict] = {
    "welcome": {
        "group": "Старт", "title": "Приветствие",
        "vars": ["name", "free", "balance"],
        "text": (
            "Привет, {name}! Это <b>Evaluation C&amp;C</b> — честная оценка твоего сайта от команды C&amp;C.\n\n"
            "<b>Как это работает</b>\n"
            "1. Пришли скриншоты или видео сайта — до 10 файлов.\n"
            "2. Добавь ссылку и что важно проверить.\n"
            "3. Получи оценку по пяти пунктам и советы, что улучшить.\n\n"
            "Каждому — <b>{free}</b> бесплатные оценки сайта.\n"
            "{balance}"
        ),
    },
    "how": {
        "group": "Старт", "title": "Как отправить сайт",
        "vars": [],
        "text": (
            "<b>Пришли скриншоты или видео сайта</b>\n\n"
            "Можно сразу несколько, до 10 файлов. Лучше всего: главный экран, пару страниц и вид с телефона. "
            "Видео — коротко пролистай сайт.\n\n"
            "Следом напиши ссылку и что важно оценить — и нажми «Отправить на оценку»."
        ),
    },
    "accepted": {
        "group": "Заявка", "title": "Заявка принята",
        "vars": ["id", "balance"],
        "text": (
            "<b>Заявка #{id} принята</b>\n\n"
            "Команда посмотрит сайт и пришлёт оценку сюда. Обычно это не дольше суток.\n{balance}"
        ),
    },
    "taken": {
        "group": "Заявка", "title": "Взяли в работу",
        "vars": ["id", "admin"],
        "text": "<b>Заявку #{id} взяли в работу</b>\n\nСмотрит {admin}. Оценка придёт сюда.",
    },
    "result_outro": {
        "group": "Заявка", "title": "Подпись под оценкой",
        "vars": [],
        "text": "Есть вопрос по оценке — нажми «Ответить» и напиши.",
    },
    "rejected": {
        "group": "Заявка", "title": "Заявку отклонили",
        "vars": ["id", "reason"],
        "text": (
            "<b>Заявку #{id} не получилось оценить</b>\n\n{reason}\n\n"
            "Оценку мы вернули на баланс — можно отправить сайт заново."
        ),
    },
    "limit": {
        "group": "Заявка", "title": "Оценки закончились",
        "vars": ["free"],
        "text": (
            "<b>Бесплатные оценки закончились</b>\n\n"
            "Ты уже отправил {free} сайта на оценку. Новые оценки скоро появятся — следи за ботом."
        ),
    },
    "pay_offer": {
        "paid": True,
        "group": "Оплата", "title": "Бесплатные закончились",
        "vars": ["price", "stars"],
        "text": (
            "<b>Бесплатные оценки закончились</b>\n\n"
            "Одна оценка сайта — <b>{price} ₽</b>. Оплати удобным способом и сразу отправляй сайт."
        ),
    },
    "transfer": {
        "paid": True,
        "group": "Оплата", "title": "Оплата переводом",
        "vars": ["contact", "id", "price"],
        "text": (
            "Напиши {contact}: «Хочу оценку сайта» и свой ID — <code>{id}</code>.\n"
            "После перевода {price} ₽ оценку добавят на баланс, и бот пришлёт сообщение."
        ),
    },
    "paid": {
        "paid": True,
        "group": "Оплата", "title": "Оплата прошла",
        "vars": ["balance"],
        "text": "<b>Оплата прошла</b>, спасибо!\n{balance}\n\nПрисылай скриншоты или видео сайта.",
    },
}

VAR_TITLES = {
    "name": "имя человека", "free": "сколько бесплатных", "price": "цена в рублях", "stars": "цена в звёздах",
    "balance": "строка с балансом", "id": "номер заявки или ID", "admin": "кто оценивает",
    "reason": "причина", "contact": "кому писать",
}

_TAG_RE = re.compile(
    r"&lt;(?:(?P<close>/)(?P<ctag>b|i|u|s|code|a|blockquote|tg-spoiler)"
    r"|(?P<otag>b|i|u|s|code|blockquote|tg-spoiler)"
    r"|a href=&quot;(?P<href>https?://[^\s\"<>]+?|tg://[^\s\"<>]+?)&quot;)&gt;"
)


def telegram_html(text: str) -> str:
    """Оставляет только теги, которые понимает Telegram, и всегда закрывает их в правильном порядке."""
    escaped = html.escape(html.unescape(text or ""), quote=True)
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(escaped):
        out.append(escaped[pos:match.start()])
        pos = match.end()
        if match.group("close"):
            tag = match.group("ctag")
            if stack and stack[-1] == tag:
                stack.pop()
                out.append(f"</{tag}>")
            else:
                out.append(match.group(0))
        elif match.group("otag"):
            if "code" in stack:
                out.append(match.group(0))
            else:
                stack.append(match.group("otag"))
                out.append(f"<{match.group('otag')}>")
        else:
            if "a" in stack or "code" in stack:
                out.append(match.group(0))
            else:
                stack.append("a")
                out.append(f'<a href="{match.group("href")}">')
    out.append(escaped[pos:])
    out.extend(f"</{tag}>" for tag in reversed(stack))
    return "".join(out).strip()


def plain_len(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text or "")))


def fill(text: str, values: dict) -> str:
    """Подставляет значения. Значения — уже готовый HTML (экранирует вызывающий код)."""
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
