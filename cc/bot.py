"""Бот C&C Family: /start, оплата, ответ на всё остальное. Всё нужное — в мини-аппе."""
from __future__ import annotations

import logging
import time

from aiogram import Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    ChatJoinRequest,
    BotCommand, BotCommandScopeAllChatAdministrators, BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats, BotCommandScopeChat, BotCommandScopeDefault, ChatMemberUpdated,
    MenuButtonWebApp, Message, PreCheckoutQuery, WebAppInfo,
)

from . import access, config, db, payments
from .tg import bot

log = logging.getLogger("cc.bot")
main_router = Router(name="core")
fallback_router = Router(name="core-fallback")
private = F.chat.type == ChatType.PRIVATE


def support_button():
    return access.url_button("Поддержка", config.SUPPORT_USERNAME)


@main_router.message(CommandStart(), private)
async def start(message: Message, command: CommandObject | None = None) -> None:
    tg_user = message.from_user
    source = (command.args or "") if command else ""
    user = await db.upsert_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name,
                                started=True, source=source)
    if user.get("banned"):
        await message.answer("Доступ закрыт. Если это ошибка, напиши в поддержку.",
                             reply_markup=access.keyboard([support_button()]))
        return
    await db.log_event(tg_user.id, "start", source)
    body = await access.text("welcome")
    markup = access.keyboard([access.app_button("Открыть C&C Family")])
    await access.send(tg_user.id, body, markup, image="welcome")
    if config.PUBLIC_URL:
        await set_menu(tg_user.id)


# ---------- Оплата картой и звёздами (счёт Telegram) ----------

@main_router.pre_checkout_query(F.invoice_payload.startswith("cc:"))
async def pre_checkout(query: PreCheckoutQuery) -> None:
    payment = await payments.payment_from_payload(query.invoice_payload)
    ok = bool(
        payment and payment["status"] == "pending" and payment["user_id"] == query.from_user.id
        and query.total_amount == payments.expected_total(payment)
    )
    await query.answer(ok=ok, error_message=None if ok else
                       "Счёт устарел. Открой оплату в приложении ещё раз — займёт секунду.")


@main_router.message(F.successful_payment, F.successful_payment.invoice_payload.startswith("cc:"))
async def paid(message: Message) -> None:
    info = message.successful_payment
    payment = await payments.payment_from_payload(info.invoice_payload)
    if not payment:
        log.error("Оплата без счёта: %s", info.invoice_payload)
        return
    await complete_payment(payment, note=info.telegram_payment_charge_id or "")


async def complete_payment(payment: dict, note: str = "", until: int | None = None) -> bool:
    """Отмечает оплату и открывает доступ. Повторное уведомление ничего не делает.
    until — точная дата окончания (подписка Tribute), иначе продлеваем на дни тарифа."""
    if not await db.mark_paid(payment["id"], note):
        return False
    if until:
        await access.grant_until(payment["user_id"], payment["tariff"], until)
    else:
        await access.grant(payment["user_id"], payment["tariff"], int(payment["days"]))
    user = await db.get_user(payment["user_id"]) or {}
    who = f"@{user['username']}" if user.get("username") else (user.get("first_name") or str(payment["user_id"]))
    amount = f"{payment['amount']:.0f} ⭐" if payment["method"] == "stars" else f"{payment['amount']:.0f} ₽"
    method = {"card": "картой", "tribute": "картой (Tribute)", "crypto": "криптой", "stars": "звёздами",
              "manual": "вручную"}.get(payment["method"], "")
    for admin_id in config.ADMIN_IDS:
        await access.send(admin_id, f"<b>Оплата</b> {amount} {method}: {who} · тариф «{payment['tariff']}»")
    return True


# ---------- Закрытая группа: кто вошёл и вышел ----------

@main_router.chat_member()
async def group_member(update: ChatMemberUpdated) -> None:
    if not config.GROUP_ID or update.chat.id != config.GROUP_ID:
        return
    uid = update.new_chat_member.user.id
    if update.new_chat_member.user.is_bot:
        return
    status = update.new_chat_member.status
    status = getattr(status, "value", status)
    inside = status in ("creator", "administrator", "member") or (
        status == "restricted" and getattr(update.new_chat_member, "is_member", False))
    user = await db.get_user(uid)
    if not user:
        u = update.new_chat_member.user
        user = await db.upsert_user(uid, u.username, u.first_name, u.last_name)
    await db.update_user(uid, group_member=int(inside), group_checked=int(time.time()))
    await access.sync_modules(dict(user, group_member=int(inside)))


@main_router.chat_join_request()
async def join_request(request: ChatJoinRequest) -> None:
    """Заявка в закрытую группу или чат резидентов: резидента пускаем сразу, остальным — тарифы.
    После оплаты бот одобряет отложенные заявки сам."""
    chat = request.chat.id
    is_group = bool(config.GROUP_ID) and chat == config.GROUP_ID
    is_chat = (config.CHAT_ID and chat == config.CHAT_ID) or (not is_group and not config.CHAT_ID)
    if not (is_group or is_chat):
        return
    u = request.from_user
    user = await db.upsert_user(u.id, u.username, u.first_name, u.last_name)
    chat_id = request.user_chat_id or u.id
    where = "закрытую группу" if is_group else "чат резидентов"
    if db.is_resident(user):
        try:
            await request.approve()
            await access.send(chat_id, f"Заявку в {where} C&amp;C Family одобрил, заходи)")
        except TelegramAPIError as exc:
            log.warning("Не удалось одобрить заявку %s: %s", u.id, exc)
        return
    if is_group:
        await db.update_user(u.id, join_requested=1)
    else:
        await db.update_user(u.id, chat_requested=chat)
    await access.send(chat_id, f"Привет) {where.capitalize()} — для резидентов C&amp;C Family.\n\n"
                               "Оформи доступ в приложении, и я сразу одобрю твою заявку. "
                               "Бесплатные уроки, марафон и навигация доступны и без оплаты.",
                      access.keyboard([access.app_button("Тарифы", "#join")], [support_button()]))


@main_router.my_chat_member(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def added_to_group(update: ChatMemberUpdated) -> None:
    """Бота добавили в группу — подсказываем админам её ID для переменной GROUP_ID."""
    status = update.new_chat_member.status
    status = getattr(status, "value", status)
    if status not in ("administrator", "member") or update.chat.id in (config.GROUP_ID, config.CHAT_ID):
        return
    rights = "Бот уже админ." if status == "administrator" else (
        "Сделай бота админом с правами «Пригласительные ссылки» и «Блокировка участников».")
    for admin_id in config.ADMIN_IDS:
        await access.send(admin_id, f"Бота добавили в группу «{update.chat.title or ''}».\n"
                                    f"Её ID: <code>{update.chat.id}</code>.\n"
                                    "Если это закрытая группа — впиши ID в переменную GROUP_ID на Railway, "
                                    f"если чат резидентов — в CHAT_ID.\n{rights}")


@main_router.my_chat_member(private)
async def bot_status(update: ChatMemberUpdated) -> None:
    status = update.new_chat_member.status
    status = getattr(status, "value", status)
    await db.update_user(update.from_user.id, blocked_bot=int(status == "kicked"))


# ---------- Всё остальное: бот только открывает приложение ----------

@fallback_router.message(private)
async def fallback(message: Message) -> None:
    tg_user = message.from_user
    if tg_user:
        await db.upsert_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name, started=True)
    markup = access.keyboard([access.app_button("Открыть C&C")], [support_button()])
    await message.answer(await access.text("fallback"), reply_markup=markup)


# ---------- Меню, команды, описание ----------

async def set_menu(chat_id: int | None = None) -> None:
    """Кнопка слева от поля ввода: «C&C» открывает приложение."""
    if not config.PUBLIC_URL:
        return
    button = MenuButtonWebApp(text="C&C", web_app=WebAppInfo(url=config.app_url("")))
    try:
        if chat_id:
            await bot.set_chat_menu_button(chat_id=chat_id, menu_button=button)
        else:
            await bot.set_chat_menu_button(menu_button=button)
    except TelegramAPIError as exc:
        log.info("Не удалось поставить кнопку меню: %s", exc)


async def setup_bot() -> None:
    """Только /start в списке команд, кнопка C&C, описание «Что умеет этот бот?»."""
    try:
        me = await bot.get_me()
        if me.username and me.username.lower() != config.BOT_USERNAME.lower():
            log.warning("BOT_USERNAME=%s, а бот на самом деле @%s — ссылки берём из настоящего.",
                        config.BOT_USERNAME, me.username)
            config.BOT_USERNAME = me.username
    except TelegramAPIError:
        log.exception("Не удалось получить данные бота")
    commands = [BotCommand(command="start", description="Открыть C&C Family")]
    for scope in (BotCommandScopeAllPrivateChats(), BotCommandScopeAllGroupChats(),
                  BotCommandScopeAllChatAdministrators()):
        try:
            await bot.delete_my_commands(scope=scope)
        except TelegramAPIError:
            pass
    for admin_id in config.ADMIN_IDS:  # у старых ботов админам ставили длинные списки команд
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError:
            pass
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except TelegramAPIError:
        log.exception("Не удалось поставить команды")
    description = await db.get_setting("bot_description", None) or (
        "Приватка C&C Family про вайбкодинг и нейросети: курс с нуля, парсер клиентов, скрипты для "
        "переписки, AI-офис, оценка работ и марафон «Первый заказ». Всё внутри приложения, первые уроки открыты бесплатно."
    )
    try:
        await bot.set_my_description(description[:512])
        await bot.set_my_short_description(
            "Приватка C&C Family про вайбкодинг: курс, парсер, скрипты, разборы."[:120])
    except TelegramAPIError:
        log.info("Не удалось обновить описание бота")
    await set_menu()


def build_dispatcher() -> Dispatcher:
    from modules.evaluation.bot import dp as evaluation_router

    dp = Dispatcher()
    dp.include_router(main_router)
    dp.include_router(evaluation_router)  # переписка по заявкам на оценку
    dp.include_router(fallback_router)    # всё остальное — «бот только открывает приложение»
    return dp


async def run_bot() -> None:
    await setup_bot()
    dp = build_dispatcher()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
