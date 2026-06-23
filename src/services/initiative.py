"""Алиса (или активная) пишет первой, когда юзер молчит."""
from __future__ import annotations

import asyncio
import datetime
import random
import time

from aiogram import Bot
from aiogram.enums import ChatAction

from src.character.persona import build_system_prompt
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService
from src.utils.logger import get_logger
from src.utils.text import split_messages, strip_asterisks, typing_pause

logger = get_logger(__name__)

CHECK_INTERVAL_SEC = 15 * 60
SILENT_AFTER_HOURS = 3.0
MIN_GAP_BETWEEN_INITIATIVES_HOURS = 4.0
ALLOWED_HOUR_FROM = 9
ALLOWED_HOUR_TO = 23


def _moscow_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)


async def initiative_loop(
    bot: Bot, llm: OpenRouterClient, memory: ChatMemory,
    weather: WeatherService, storage: ProfileStorage,
) -> None:
    logger.info(
        "Инициатива: каждые %d мин, после %.1f ч, окно %d-%d МСК",
        CHECK_INTERVAL_SEC // 60, SILENT_AFTER_HOURS,
        ALLOWED_HOUR_FROM, ALLOWED_HOUR_TO,
    )
    await asyncio.sleep(60)
    while True:
        try:
            await _tick(bot, llm, memory, weather, storage)
        except Exception as e:  # noqa: BLE001
            logger.exception("initiative tick failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


async def _tick(bot, llm, memory, weather, storage):
    now = _moscow_now()
    if not (ALLOWED_HOUR_FROM <= now.hour <= ALLOWED_HOUR_TO):
        return
    now_ts = time.time()

    for user_id in memory.all_consented_users():
        last_user = memory.get_last_activity(user_id)
        last_init = memory.get_last_initiative(user_id)
        if last_user == 0:
            continue
        if (now_ts - last_user) / 3600 < SILENT_AFTER_HOURS:
            continue
        if (now_ts - last_init) / 3600 < MIN_GAP_BETWEEN_INITIATIVES_HOURS:
            continue
        if random.random() > 0.4:
            continue
        await _send_initiative(bot, llm, memory, weather, storage, user_id)


async def _send_initiative(bot, llm, memory, weather, storage, user_id):
    profile = await storage.get(user_id)
    girl = profile.get_active_girl()
    logger.info("Initiative → user=%s, girl=%s", user_id, girl.name)

    history = await memory.get_history(user_id, girl.id)
    facts = await memory.get_facts(user_id, girl.id)
    system = build_system_prompt(
        girl=girl,
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=_moscow_now(),
        facts=facts,
        style="initiative",
    )
    messages = [{"role": "system", "content": system}, *history]
    messages.append({"role": "user", "content": "(он молчит, напиши ему сама первой)"})

    try:
        reply = await llm.chat(messages, temperature=1.0, max_tokens=300)
    except Exception as e:  # noqa: BLE001
        logger.warning("Initiative LLM failed: %s", e)
        return

    reply = strip_asterisks(reply.strip())
    if not reply:
        return

    await memory.add_assistant(user_id, girl.id, reply)
    memory.mark_initiative(user_id)

    parts = split_messages(reply, max_parts=3)
    for part in parts:
        try:
            await bot.send_chat_action(user_id, ChatAction.TYPING)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(typing_pause(part))
        try:
            await bot.send_message(user_id, part)
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог отправить инициативу user=%s: %s", user_id, e)
            return
