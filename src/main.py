"""Точка входа."""
from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from src.bot.handlers import get_root_router
from src.bot.middlewares.dependencies import DependenciesMiddleware
from src.bot.middlewares.whitelist import WhitelistMiddleware
from src.bot.tg_menu import setup_menu
from src.config import settings
from src.services.initiative import initiative_loop
from src.services.keepalive import keepalive_loop
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService
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
    dp = Dispatcher(storage=MemoryStorage())

    llm = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        models=settings.openrouter_models_chain,
    )
    memory = ChatMemory(max_messages=settings.history_size)
    weather = WeatherService()
    profiles = ProfileStorage()

    for observer in (dp.message, dp.callback_query):
        observer.middleware(WhitelistMiddleware(settings.allowed_user_ids))
        observer.middleware(DependenciesMiddleware(llm, memory, weather, profiles))

    dp.include_router(get_root_router())

    http_runner = await _start_http_server()
    logger.info("HTTP on port %s", os.environ.get("PORT", "8080"))

    keepalive_task = asyncio.create_task(keepalive_loop())
    initiative_task = asyncio.create_task(
        initiative_loop(bot, llm, memory, weather, profiles)
    )

    logger.info("Жду 15 сек перед polling…")
    await asyncio.sleep(15)

    try:
        await setup_menu(bot)
        logger.info("Меню установлено.")
    except Exception as e:  # noqa: BLE001
        logger.warning("Меню не установилось: %s", e)

    logger.info(
        "Bot is starting… models=%s", " → ".join(settings.openrouter_models_chain)
    )
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Bot shutting down…")
        keepalive_task.cancel()
        initiative_task.cancel()
        await weather.close()
        await llm.close()
        await bot.session.close()
        await http_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
