"""
Алиса пишет первой, когда пользователь молчит.

Раз в N минут проверяем всех consented юзеров:
- сколько прошло с их последнего сообщения
- сколько прошло с последней нашей инициативы
- сейчас разумное время по Москве (не глубокая ночь)
Если все условия выполнены — генерим короткое сообщение и шлём.
"""
from __future__ import annotations

import asyncio
import datetime
import random

from aiogram import Bot

from src.character.persona import build_system_prompt
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient
from src.services.weather import WeatherService
from src.utils.logger import get_logger
from src.utils.text import asterisks_to_italic, split_messages, typing_pause

logger = get_logger(__name__)

# Как часто просыпается фоновый воркер.
CHECK_INTERVAL_SEC = 15 * 60

# Минимальная тишина пользователя, после которой Алиса имеет право написать.
SILENT_AFTER_HOURS = 3.0

# Минимальный промежуток между её инициативами (чтобы не спамила).
MIN_GAP_BETWEEN_INITIATIVES_HOURS = 4.0

# В какие часы по Москве можно писать (ночью не дёргаем).
ALLOWED_HOUR_FROM = 9
ALLOWED_HOUR_TO = 23  # включительно — до 23:59


def _moscow_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)


async def initiative_loop(
    bot: Bot,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
) -> None:
    logger.info(
        "Инициатива: каждые %d мин, после %.1f ч молчания, окно %d-%d МСК",
        CHECK_INTERVAL_SEC // 60, SILENT_AFTER_HOURS,
        ALLOWED_HOUR_FROM, ALLOWED_HOUR_TO,
    )
    # Сразу не дёргаем — даём боту нормально подняться.
    await asyncio.sleep(60)

    while True:
        try:
            await _tick(bot, llm, memory, weather)
        except Exception as e:  # noqa: BLE001
            logger.exception("initiative tick failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


async def _tick(
    bot: Bot,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
) -> None:
    now = _moscow_now()
    if not (ALLOWED_HOUR_FROM <= now.hour <= ALLOWED_HOUR_TO):
        return

    import time as _time
    now_ts = _time.time()

    for user_id in memory.all_consented_users():
        last_user = memory.get_last_activity(user_id)
        last_init = memory.get_last_initiative(user_id)

        if last_user == 0:
            continue  # ни разу не писал
        silent_h = (now_ts - last_user) / 3600
        if silent_h < SILENT_AFTER_HOURS:
            continue
        gap_h = (now_ts - last_init) / 3600
        if gap_h < MIN_GAP_BETWEEN_INITIATIVES_HOURS:
            continue

        # Не каждый раз — добавим элемент случайности (40% шанс),
        # иначе будет слишком предсказуемо.
        if random.random() > 0.4:
            continue

        await _send_initiative(bot, llm, memory, weather, user_id)


async def _send_initiative(
    bot: Bot,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
    user_id: int,
) -> None:
    logger.info("Initiative → user=%s", user_id)

    system = build_system_prompt(
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=_moscow_now(),
        style="initiative",
    )
    # Для инициативы тоже даём историю — чтобы помнила контекст.
    messages = [{"role": "system", "content": system}, *memory.get_history(user_id)]
    # Подталкиваем модель «сгенерируй сама без вопроса».
    messages.append({"role": "user", "content": "(он молчит, напиши ему сама первой)"})

    try:
        reply = await llm.chat(messages, temperature=1.0, max_tokens=300)
    except Exception as e:  # noqa: BLE001
        logger.warning("Initiative LLM failed: %s", e)
        return

    reply = reply.strip()
    if not reply:
        return

    # Сохраняем в историю как обычный ответ Алисы (важно для контекста).
    memory.add_assistant(user_id, reply)
    memory.mark_initiative(user_id)

    parts = split_messages(reply, max_parts=2)
    for i, part in enumerate(parts):
        if i > 0:
            await asyncio.sleep(typing_pause(part))
        try:
            await bot.send_message(user_id, asterisks_to_italic(part))
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог отправить инициативу user=%s: %s", user_id, e)
            return
