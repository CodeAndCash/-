import io
import re
from urllib.parse import urlencode

from aiogram.types import BufferedInputFile
from openpyxl import Workbook
from openpyxl.styles import Font

from . import countries
from . import db

HEADERS = ["Название", "Ниша", "Страна", "Город", "Адрес", "Номер телефона", "Статус"]
NOT_FOUND = "не найдено"
STATUS_NAMES = {
    "new": "Новый",
    "written": "Написал",
    "replied": "Ответил",
    "rejected": "Отказ",
    "client": "Клиент",
}


def _safe_spreadsheet_text(value) -> str:
    """Prevent user-provided OSM text from being interpreted as an Excel formula."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def yandex_link(lead: dict) -> str:
    """Ссылка на Яндекс Карты: точка бизнеса (если есть координаты) + поиск по названию и адресу."""
    info = lead.get("info") or {}
    address = (lead.get("c") or {}).get("address") or info.get("address") or ""
    query = ", ".join(part for part in (lead.get("name", ""), address or lead.get("city", "")) if part)
    params = {"text": query}
    lat, lon = info.get("lat"), info.get("lon")
    if lat and lon:
        params.update(ll=f"{lon},{lat}", z="17", pt=f"{lon},{lat}")
    return "https://yandex.ru/maps/?" + urlencode(params)


def build_xlsx(leads: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Клиенты"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    link_font = Font(color="1F5FBF", underline="single")
    for lead in leads:
        contacts = lead.get("c") or {}
        info = lead.get("info") or {}
        address = contacts.get("address") or info.get("address") or ""
        country = countries.TITLES.get((lead.get("country") or "").upper(), lead.get("country", ""))
        values = [
            lead["name"],
            lead.get("niche") or info.get("niche", ""),
            country,
            lead.get("city", ""),
            address or "Открыть на карте",
            ", ".join(info.get("phones") or []) or lead.get("phone") or NOT_FOUND,
            STATUS_NAMES.get(lead.get("status"), lead.get("status", "")),
        ]
        row = [_safe_spreadsheet_text(value) for value in values]
        if re.fullmatch(r"[+\d][\d\s()+,\-]*", values[5] or ""):
            row[5] = values[5]  # номер телефона хранится как текст, «+» не формула
        sheet.append(row)
        cell = sheet.cell(row=sheet.max_row, column=5)
        cell.hyperlink = yandex_link(lead)
        cell.font = link_font

    for index, width in enumerate([32, 20, 14, 18, 42, 26, 12], start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def send_export(uid: int) -> None:
    from .bot import bot

    leads = await db.list_leads(uid, "all", 100000)
    if not leads:
        await bot.send_message(uid, "<b>Пока нет лидов</b>\n\nНайдите бизнесы в приложении — потом их можно выгрузить в Excel.")
        return
    data = build_xlsx(leads)
    await bot.send_document(
        uid,
        BufferedInputFile(data, filename="parser_cc_leads.xlsx"),
        caption=f"<b>Ваши лиды</b>\n\nВ файле: <b>{len(leads)}</b>",
    )
