"""Бот: /start, ответ на любое сообщение, переписка по заявке, только /start в меню."""
import asyncio
import datetime as dt

from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    DeleteMyCommands, GetMe, SendAnimation, SendMessage, SendPhoto, SetChatMenuButton, SetMyCommands, SetMyDescription,
    SetMyShortDescription,
)
from aiogram.types import Animation, Chat, Message, PhotoSize, Update, User

from cc import config


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        chat = Chat(id=getattr(method, "chat_id", 1) or 1, type="private")
        if isinstance(method, (SendMessage, SendPhoto, SendAnimation)):
            photo = [PhotoSize(file_id="P", file_unique_id="U", width=1, height=1)] if isinstance(method, SendPhoto) else None
            anim = (Animation(file_id="A", file_unique_id="UA", width=1280, height=640, duration=6)
                    if isinstance(method, SendAnimation) else None)
            return Message(message_id=1, date=dt.datetime.now(), chat=chat, text=getattr(method, "text", None),
                           photo=photo, animation=anim)
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="C&C", username="CodeAndCash_bot")
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self):
        pass


def update(uid, text, uid_seq=[0]):
    uid_seq[0] += 1
    return Update(update_id=uid_seq[0], message=Message(
        message_id=uid_seq[0], date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="Тест", username=f"u{uid}"), text=text))


def run_with(session, coro_factory):
    from cc.tg import bot
    old = bot.session
    bot.session = session
    try:
        return asyncio.run(coro_factory())
    finally:
        bot.session = old


def test_start_fallback_and_eval_dialog():
    from cc import db
    from cc.bot import build_dispatcher
    from modules.evaluation import bot as eval_bot
    session = FakeSession()

    async def scenario():
        await db.init()
        from modules.evaluation import db as eval_db
        await eval_db.init()
        dp = build_dispatcher()
        from cc.tg import bot
        await dp.feed_update(bot, update(9001, "/start"))
        await dp.feed_update(bot, update(9001, "привет, как оплатить?"))
        eval_bot.REPLY_TO[9001] = 5
        await dp.feed_update(bot, update(9001, "вопрос по оценке"))
        return dp

    dp = run_with(session, scenario)
    # приветствие — анимация: телефон с листающимся мини-аппом
    welcome = [c for c in session.calls if isinstance(c, SendAnimation)][0]
    assert "C&amp;C Family" in welcome.caption
    assert welcome.reply_markup.inline_keyboard[0][0].web_app.url == config.app_url("")
    fallback = [c for c in session.calls if isinstance(c, SendMessage) and "Бот только открывает приложение" in c.text][0]
    texts = [b.text for row in fallback.reply_markup.inline_keyboard for b in row]
    assert texts == ["Открыть C&C", "Поддержка"]
    # ответ по заявке ушёл в модуль оценок, а не в общий ответ
    assert any(isinstance(c, SendMessage) and "Передал команде" in c.text for c in session.calls)
    assert "chat_member" in dp.resolve_used_update_types()


def test_only_start_command_and_menu_button():
    from cc.bot import setup_bot
    session = FakeSession()
    run_with(session, setup_bot)
    commands = [c for c in session.calls if isinstance(c, SetMyCommands)]
    assert len(commands) == 1 and [x.command for x in commands[0].commands] == ["start"]
    assert any(isinstance(c, DeleteMyCommands) for c in session.calls)
    menu = [c for c in session.calls if isinstance(c, SetChatMenuButton)][0]
    assert menu.menu_button.text == "C&C"
    assert any(isinstance(c, SetMyDescription) for c in session.calls)
    assert any(isinstance(c, SetMyShortDescription) for c in session.calls)
