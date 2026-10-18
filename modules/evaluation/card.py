"""Картинка-оценка 1080×1350 в стиле C&C: итог, вывод и полоски по критериям."""
from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont

from .db import CRITERIA
from .render import fmt_score, verdict

ASSETS = Path(__file__).resolve().parent / "assets"
W, H = 1080, 1350
BG = (243, 243, 244)
INK = (21, 22, 25)
MUTED = (109, 112, 119)
LINE = (220, 221, 224)
CARD = (255, 255, 255)
SOFT = (230, 231, 234)


def _font(name: str, size: int, weight: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(ASSETS / "fonts" / f"{name}.ttf"), size)
    try:
        font.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass
    return font


def _bird(size: int, color=INK) -> Image.Image:
    mask = Image.open(ASSETS / "bird.png").convert("RGBA").split()[-1].resize((size, size), Image.LANCZOS)
    img = Image.new("RGBA", (size, size), color + (0,))
    img.putalpha(mask)
    solid = Image.new("RGBA", (size, size), color + (255,))
    solid.putalpha(mask)
    return solid


def _domain(url: str) -> str:
    try:
        host = urlsplit(url if "://" in url else "https://" + url).hostname or ""
    except ValueError:
        host = ""
    return host.removeprefix("www.")[:40]


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def render_card(review: dict, brand: str = "Evaluation C&C") -> bytes:
    scores = review.get("scores") or {}
    total = float(review.get("total") or 0)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # точечная сетка фона
    for y in range(22, H, 44):
        for x in range(22, W, 44):
            d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(214, 215, 219))

    head = _font("Unbounded", 34, "ExtraBold")
    small = _font("Manrope", 28, "SemiBold")
    tiny = _font("Manrope", 24, "Bold")

    # шапка
    img.paste(_bird(58), (72, 64), _bird(58))
    d.text((146, 70), brand, font=head, fill=INK)
    tag = f"#{review.get('id', '')}"
    tw = d.textlength(tag, font=tiny)
    d.rounded_rectangle((W - 72 - tw - 36, 70, W - 72, 116), radius=23, fill=INK)
    d.text((W - 72 - tw - 18, 79), tag, font=tiny, fill=(255, 255, 255))

    # итог
    d.rounded_rectangle((60, 160, W - 60, 560), radius=44, fill=INK)
    big = _font("Unbounded", 190, "Black")
    score = fmt_score(total)
    d.text((110, 205), score, font=big, fill=(255, 255, 255))
    sw = d.textlength(score, font=big)
    d.text((110 + sw + 18, 360), "/ 10", font=_font("Unbounded", 52, "Bold"), fill=(150, 152, 158))
    d.text((112, 452), verdict(total), font=_font("Unbounded", 40, "Bold"), fill=(255, 255, 255))
    domain = _domain(review.get("url") or "")
    sub = f"Оценка сайта {domain}" if domain else "Оценка сайта по скриншотам и видео"
    d.text((112, 506), _fit(d, sub, small, W - 300), font=small, fill=(170, 172, 178))
    img.paste(_bird(150, (255, 255, 255)), (W - 230, 205), _bird(150, (255, 255, 255)))

    # критерии
    label = _font("Manrope", 36, "ExtraBold")
    num = _font("Unbounded", 38, "ExtraBold")
    y = 610
    for key, title in CRITERIA:
        if key not in scores:
            continue
        value = float(scores[key])
        d.rounded_rectangle((60, y, W - 60, y + 118), radius=34, fill=CARD, outline=LINE, width=2)
        d.text((100, y + 22), title, font=label, fill=INK)
        val = fmt_score(value)
        vw = d.textlength(val, font=num)
        d.text((W - 100 - vw, y + 20), val, font=num, fill=INK)
        x0, x1, by = 100, W - 100, y + 82
        d.rounded_rectangle((x0, by, x1, by + 14), radius=7, fill=SOFT)
        filled = x0 + (x1 - x0) * max(0.0, min(1.0, value / 10))
        if filled > x0 + 14:
            d.rounded_rectangle((x0, by, filled, by + 14), radius=7, fill=INK)
        y += 134

    # подпись
    who = review.get("admin_name") or ""
    foot = f"Оценивал {who}" if who else brand
    d.text((72, H - 76), _fit(d, foot, small, W - 160), font=small, fill=MUTED)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
