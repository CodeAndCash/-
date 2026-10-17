"""Один экземпляр бота на весь проект: им пользуются ядро и все модули."""
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import config

# Пустой токен бывает только в тестах — Bot требует токен правильного вида.
bot = Bot(config.BOT_TOKEN or "1:placeholder", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
