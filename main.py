"""Запуск C&C Family: сервер мини-аппа + бот + фоновые задачи в одном процессе."""
import asyncio
import logging
import time

import uvicorn

from cc import config


async def poll_crypto() -> None:
    from cc import db
    from cc.api import check_crypto

    from cc.api import check_xrocket

    if config.CRYPTO_PAY_TOKEN:
        await check_crypto(await db.pending_payments("crypto", newer_than=int(time.time()) - 2 * 3600))
    if config.XROCKET_PAY_TOKEN:
        await check_xrocket(await db.pending_payments("xrocket", newer_than=int(time.time()) - 2 * 3600))


async def main() -> None:
    config.validate_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    # Импорт после проверки настроек — пустой токен даёт понятную ошибку.
    from cc import access
    from cc.api import app
    from cc.bot import run_bot
    from cc.tg import bot

    server = uvicorn.Server(uvicorn.Config(app, host=config.API_HOST, port=config.API_PORT, log_level="info",
                                           loop="asyncio", access_log=False))
    tasks = {
        asyncio.create_task(server.serve(), name="server"),
        asyncio.create_task(run_bot(), name="bot"),
        asyncio.create_task(access.loop("abandoned", access.process_abandoned, 30), name="abandoned"),
        asyncio.create_task(access.loop("expiry", access.process_expiry, 300), name="expiry"),
        asyncio.create_task(access.loop("crypto", poll_crypto, 20), name="crypto"),
        asyncio.create_task(access.loop("marathon", access.process_marathon, 900), name="marathon"),
    }
    main_tasks = {t for t in tasks if t.get_name() in ("server", "bot")}
    try:
        # Остановился бот или сервер (например, Railway обновляет версию) — останавливаем всё.
        await asyncio.wait(main_tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in main_tasks:
            if task.done() and not task.cancelled() and task.exception():
                logging.getLogger("main").error("Остановилось с ошибкой", exc_info=task.exception())
    finally:
        server.should_exit = True
        for task in tasks:
            if not task.done() and task.get_name() != "server":
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
