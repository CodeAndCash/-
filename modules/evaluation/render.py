"""Тексты, которые бот отправляет людям: оценка, сообщения, статусы (HTML-разметка Telegram)."""
from __future__ import annotations

import html
import re

from .db import CRITERIA


def esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


def bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(float(score))))
    return "▰" * filled + "▱" * (width - filled)


def verdict(total: float) -> str:
    if total >= 8.5:
        return "Отличный сайт"
    if total >= 7:
        return "Хороший сайт"
    if total >= 5:
        return "Есть над чем поработать"
    return "Сайт стоит переделать"


def fmt_score(value: float) -> str:
    value = round(float(value), 1)
    return str(int(value)) if value == int(value) else str(value).replace(".", ",")


def review_result(review: dict, outro: str = "Есть вопрос по оценке — нажмите «Ответить» и напишите.") -> str:
    scores = review.get("scores") or {}
    has_total = review.get("total") is not None and bool(scores)
    lines = [f"<b>Оценка сайта готова</b> · заявка #{review['id']}", ""]
    if has_total:
        total = float(review["total"])
        lines += [f"<b>Итог: {fmt_score(total)} из 10</b>", f"{bar(total)}  {verdict(total)}", ""]
    body = str(review.get("body") or "").strip()
    if body:
        lines += [body, ""]  # уже очищенный HTML Telegram
    notes = review.get("notes") or {}
    for key, title in CRITERIA:
        if key in scores:
            lines.append(f"<b>{title}</b> — {fmt_score(scores[key])}/10")
            lines.append(f"<code>{bar(scores[key])}</code>")
            note = str(notes.get(key) or "").strip()
            if note:
                lines.append(f"<i>{esc(note)}</i>")
            lines.append("")
        elif str(notes.get(key) or "").strip():
            lines += [f"<b>{title}</b>", f"<i>{esc(str(notes[key]).strip())}</i>", ""]
    blocks = (
        ("Что сделано хорошо", review.get("pros")),
        ("Что мешает", review.get("cons")),
        ("Что улучшить в первую очередь", review.get("advice")),
    )
    for title, text in blocks:
        if text and str(text).strip():
            lines += ["", f"<b>{title}</b>", f"<blockquote>{esc(str(text).strip())}</blockquote>"]
    if review.get("admin_name"):
        lines += ["", f"Оценивал: {esc(review['admin_name'])}"]
    if outro:
        lines += ["", outro]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def admin_message(review_id: int, text: str, admin_name: str) -> str:
    return (f"<b>Сообщение по заявке #{review_id}</b>\n"
            f"<blockquote>{esc(text)}</blockquote>\n"
            f"— {esc(admin_name)}")


def taken(review_id: int, admin_name: str) -> str:
    return (f"<b>Заявку #{review_id} взяли в работу</b>\n\n"
            f"Смотрит {esc(admin_name)}. Оценка придёт сюда, обычно это не дольше суток.")


def rejected(review_id: int, reason: str) -> str:
    return (f"<b>Заявку #{review_id} не получилось оценить</b>\n\n"
            + (f"<blockquote>{esc(reason)}</blockquote>\n\n" if reason else "")
            + "Оценку мы вернули на баланс — можно отправить сайт заново.")


def user_name(user: dict) -> str:
    if user.get("username"):
        return "@" + str(user["username"])
    return str(user.get("first_name") or f"ID {user.get('id')}")
