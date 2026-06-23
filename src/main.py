"""Точка входа: HTTP healthcheck + Telegram polling + keep-alive."""
from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from src.bot.handlers import get_root_router
from src.bot.menu import setup_menu
from src.bot.middlewares.dependencies import DependenciesMiddleware
from src.bot.middlewares.whitelist import WhitelistMiddleware
from src.config import settings
from src.services.keepalive import keepalive_loop
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient
from src.utils.logger import get_logger, setup_logging


async def _healthcheck(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _start_http_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", _healthcheck)
    app.router.add_get("/healthz", _healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    await web.TCPSite(runner, host="0.0.0.0", port=port).start()
    return runner


async def main() -> None:
    setup_logging()
    logger = get_logger("main")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    llm = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
    )
    memory = ChatMemory(max_messages=settings.history_size)

    # Middlewares: применяем и к message, и к callback_query
    # (для callback_query тоже нужна проверка whitelist и dependencies).
    for observer in (dp.message, dp.callback_query):
        observer.middleware(WhitelistMiddleware(settings.allowed_user_ids))
        observer.middleware(DependenciesMiddleware(llm, memory))

    dp.include_router(get_root_router())

    http_runner = await _start_http_server()
    logger.info("HTTP on port %s", os.environ.get("PORT", "8080"))

    keepalive_task = asyncio.create_task(keepalive_loop())

    logger.info("Жду 15 сек перед polling (фикс конфликта старых инстансов)…")
    await asyncio.sleep(15)

    try:
        await setup_menu(bot)
        logger.info("Меню установлено.")
    except Exception as e:  # noqa: BLE001
        logger.warning("Меню не установилось: %s", e)

    logger.info("Bot is starting… model=%s", settings.openrouter_model)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Bot shutting down…")
        keepalive_task.cancel()
        await llm.close()
        await bot.session.close()
        await http_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
