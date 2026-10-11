"""Тексты бота и тарифы по умолчанию. Админ меняет их в мини-аппе: Админка → Тексты / Тарифы."""
from __future__ import annotations

import html
import re

# HTML-разметка Telegram: <b>, <i>, <u>, <s>, <code>, <a href="…">, <blockquote>.
TEXTS: dict[str, dict] = {
    "welcome": {
        "title": "Приветствие (/start)",
        "hint": "Картинка «Добро пожаловать» и кнопка «Открыть C&C Family» добавятся сами.",
        "text": (
            "Привет) Это бот <b>C&amp;C Family</b>: приложение про вайбкодинг и нейросети. "
            "Куча бесплатных материалов и закрытая приватка для резидентов.\n\n"
            "Внутри: курс по вайбкодингу с нуля, парсер клиентов, скрипты для переписки, "
            "AI-офис из помощников, оценка твоих работ и марафон «Первый заказ».\n\n"
            "Первые уроки и часть материалов открыты бесплатно, так что жми кнопку и заходи)"
        ),
    },
    "fallback": {
        "title": "Ответ на любое сообщение",
        "hint": "Кнопки «Открыть C&C» и «Поддержка» добавятся сами.",
        "text": (
            "Бот только открывает приложение, всё нужное внутри) Если что-то не работает "
            "или есть вопрос по оплате, пиши в поддержку."
        ),
    },
    "abandoned": {
        "title": "Открыл оплату и не оплатил",
        "hint": "Приходит через 3 минуты. Кнопки «Открыть C&C» и «Написать лично» добавятся сами.",
        "text": (
            "Видим, что ты открывал оплату C&amp;C Family, но до вступления не дошло) Всё получилось?\n\n"
            "Если карта не прошла или с криптой что-то не так, напиши в поддержку, быстро разберёмся.\n\n"
            "Остались вопросы по приватке? Можешь написать лично"
        ),
    },
    "paid": {
        "title": "Оплата прошла",
        "hint": "{until} — до какого числа доступ. Кнопка входа в группу добавится сама.",
        "text": (
            "<b>Оплата прошла, добро пожаловать в C&amp;C Family</b>\n\n"
            "Все уроки, парсер, скрипты и закрытые материалы уже открыты. {until}\n\n"
            "Заходи в закрытую группу по кнопке ниже: ссылка личная и работает один раз."
        ),
    },
    "expiring": {
        "title": "Доступ скоро закончится",
        "hint": "{date} — дата окончания.",
        "text": (
            "Доступ к C&amp;C Family заканчивается <b>{date}</b>.\n\n"
            "Чтобы не вылететь из группы и не потерять парсер и закрытые уроки, продли в приложении."
        ),
    },
    "expired": {
        "title": "Доступ закончился",
        "hint": "",
        "text": (
            "Доступ к C&amp;C Family закончился, поэтому бот убрал тебя из закрытой группы.\n\n"
            "Бесплатные уроки и марафон остаются. Вернуться можно в любой момент: тарифы в приложении."
        ),
    },
    "new_post": {
        "title": "Уведомление о новом материале",
        "hint": "{title} — название, {kind} — тип (урок, материал, промпт).",
        "text": "Вышел новый {kind}: <b>{title}</b>\n\nОткрыть можно в приложении.",
    },
    "marathon_day": {
        "title": "Марафон: открылся новый день",
        "hint": "{day} — номер дня, {title} — тема дня.",
        "text": "День {day} марафона открыт: <b>{title}</b>\n\nЗаймёт минут 20–40. Поехали)",
    },
}

DEFAULT_TARIFFS: list[dict] = [
    {
        "id": "base",
        "title": "Резидент",
        "subtitle": "Все материалы и инструменты",
        "price": 2990,
        "days": 30,
        "stars": 0,
        "active": True,
        "badge": "",
        "features": [
            "Весь курс: от первого промпта до сайта, за который платят",
            "Парсер клиентов без пробных лимитов",
            "Скрипты переписки и генератор под твою нишу",
            "Оценка твоих работ от команды",
            "Закрытая группа резидентов",
        ],
        "note": "Отменить можно когда угодно: просто не продлеваешь.",
        "tribute_link": "",
        "tribute_id": 0,
    },
    {
        "id": "mentor",
        "title": "С наставником",
        "subtitle": "Материалы, инструменты и наставник до первого кейса",
        "price": 17500,
        "days": 0,
        "stars": 0,
        "active": False,
        "weekly_seats": 1,
        "badge": "Скоро",
        "features": [
            "Всё из тарифа «Резидент» навсегда",
            "Личный наставник: план работы и созвоны",
            "Ведём до первого полноценного кейса",
            "Не дошли до кейса — возвращаем половину суммы",
        ],
        "note": "Набор открывается раз в неделю, мест мало: наставник работает с каждым лично.",
        "tribute_link": "",
        "tribute_id": 0,
    },
]

_TAG_RE = re.compile(
    r"&lt;(?:(?P<close>/)(?P<ctag>b|i|u|s|code|a|blockquote)"
    r"|(?P<otag>b|i|u|s|code|blockquote)"
    r"|a href=&quot;(?P<href>https?://[^\s\"<>]+?|tg://[^\s\"<>]+?)&quot;)&gt;"
)


def telegram_html(text: str) -> str:
    """Оставляет только теги, которые понимает Telegram, и закрывает их в правильном порядке."""
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


def fill(text: str, **values) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
