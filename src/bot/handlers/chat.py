"""Основной чат: текст и фото → LLM → ответ кусками с задержками.

Реализован антифлуд:
- Пока бот обрабатывает твоё сообщение и отвечает — новые сообщения
  СКЛАДЫВАЮТСЯ в очередь.
- Когда ответ отправлен — если в очереди что-то есть, они склеиваются в
  ОДНО следующее сообщение и Алиса отвечает на всё разом.

Долгосрочная память:
- После каждых N сообщений запускается извлечение фактов в фоне.
- Факты подмешиваются в каждый системный промпт.
"""
from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.handlers.photo_request import is_photo_request
from src.character.persona import build_system_prompt
from src.services.facts_extractor import extract_facts
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService
from src.utils.logger import get_logger
from src.utils.text import split_messages, strip_asterisks, typing_pause

logger = get_logger(__name__)
router = Router(name="chat")


# === АНТИФЛУД ===
# Для каждого user_id храним:
#   - "busy" lock: пока он установлен — бот обрабатывает предыдущий запрос
#   - "queue": список сообщений которые пришли пока busy
_busy: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_queue: dict[int, list[str]] = defaultdict(list)

# Каждые столько пар сообщений запускаем извлечение фактов.
FACTS_EVERY_N_USER_MSG = 6


# ---------- helpers ----------

async def _send_typing(message: Message, seconds: float) -> None:
    """typing indicator + гарантированное ожидание seconds."""
    elapsed = 0.0
    while elapsed < seconds:
        try:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:  # noqa: BLE001
            pass
        chunk = min(4.0, seconds - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk


def _clean_reply(text: str, girl_name: str = "") -> str:
    text = text.strip()
    prefixes = [f"{girl_name}:", f"{girl_name} —", f"{girl_name} -",
                "Алиса:", "Alice:"]
    for p in prefixes:
        if p and text.startswith(p):
            text = text[len(p):].lstrip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"«':
        text = text[1:-1].strip()
    text = strip_asterisks(text)
    return text or "…"


async def _stream_reply(message: Message, full_text: str) -> None:
    parts = split_messages(full_text, max_parts=8)
    for part in parts:
        await _send_typing(message, typing_pause(part))
        await message.answer(part)


async def _maybe_extract_facts(
    user_id: int, girl_id: str,
    memory: ChatMemory, llm: OpenRouterClient,
) -> None:
    """Раз в N сообщений извлекаем факты в фоне. С дедупом."""
    try:
        count = await memory.message_count(user_id, girl_id)
        if count == 0 or count % FACTS_EVERY_N_USER_MSG != 0:
            return
        history = await memory.get_history(user_id, girl_id)
        known = await memory.get_facts(user_id, girl_id)
        new_facts = await extract_facts(
            llm, history, known_facts=known,
            last_n=FACTS_EVERY_N_USER_MSG * 2,
        )
        for f in new_facts:
            await memory.add_fact(user_id, girl_id, f)
        if new_facts:
            logger.info("Saved %d new facts for user=%s", len(new_facts), user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Facts extraction tick failed: %s", e)


# ---------- handlers ----------

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message,
    bot: Bot,
    state: FSMContext,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
    storage: ProfileStorage,
) -> None:
    user_id = message.from_user.id

    if await state.get_state() is not None:
        return
    if not memory.has_consent(user_id):
        await message.answer("Сначала /start и подтверди возраст.")
        return
    # Запросы фото обрабатывает отдельный handler photo_request.
    if is_photo_request(message.text):
        return

    lock = _busy[user_id]

    # Бот занят? Складываем сообщение в очередь и тихо выходим.
    if lock.locked():
        _queue[user_id].append(message.text)
        try:
            await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:  # noqa: BLE001
            pass
        return

    async with lock:
        # Если в очереди уже что-то есть — склеиваем с текущим.
        text = message.text
        if _queue[user_id]:
            text = "\n".join(_queue[user_id] + [text])
            _queue[user_id].clear()

        await _process_user_message(message, bot, text, llm, memory, weather, storage)

        # После ответа — если за время обработки накопились ещё — обработать.
        while _queue[user_id]:
            queued = "\n".join(_queue[user_id])
            _queue[user_id].clear()
            await _process_user_message(message, bot, queued, llm, memory, weather, storage)


async def _process_user_message(
    message: Message, bot: Bot, text: str,
    llm: OpenRouterClient, memory: ChatMemory,
    weather: WeatherService, storage: ProfileStorage,
) -> None:
    user_id = message.from_user.id
    profile = await storage.get(user_id)
    girl = profile.get_active_girl()

    await memory.add_user(user_id, girl.id, text)
    facts = await memory.get_facts(user_id, girl.id)
    history = await memory.get_history(user_id, girl.id)

    system = build_system_prompt(
        girl=girl,
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
        facts=facts,
        style="reply",
    )
    messages = [{"role": "system", "content": system}, *history]

    try:
        reply = await llm.chat(messages, temperature=1.0)
    except OpenRouterError as e:
        await message.answer(f"❌ {e}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("LLM error")
        await message.answer(f"❌ Что-то пошло не так: {e}")
        return

    reply = _clean_reply(reply, girl.name)
    await memory.add_assistant(user_id, girl.id, reply)
    await _stream_reply(message, reply)

    # Извлечение фактов — в фоне, не блокируем ответ.
    asyncio.create_task(_maybe_extract_facts(user_id, girl.id, memory, llm))


@router.message(F.photo)
async def handle_photo(
    message: Message,
    bot: Bot,
    state: FSMContext,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
    storage: ProfileStorage,
) -> None:
    if await state.get_state() is not None:
        return
    user_id = message.from_user.id
    if not memory.has_consent(user_id):
        await message.answer("Сначала /start и подтверди возраст.")
        return

    lock = _busy[user_id]
    if lock.locked():
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        return

    async with lock:
        profile = await storage.get(user_id)
        girl = profile.get_active_girl()

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        caption = message.caption or "(прислал фото без подписи)"

        await memory.add_user(user_id, girl.id, f"[фото] {caption}")
        history = await memory.get_history(user_id, girl.id)
        facts = await memory.get_facts(user_id, girl.id)

        system = build_system_prompt(
            girl=girl,
            mood=memory.get_mood(user_id),
            weather=await weather.get(),
            now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
            facts=facts,
            style="photo",
        )
        user_content = [
            {"type": "text", "text": caption},
            {"type": "image_url", "image_url": {"url": file_url}},
        ]
        messages = [
            {"role": "system", "content": system},
            *history[:-1],
            {"role": "user", "content": user_content},
        ]

        try:
            reply = await llm.chat(messages, temperature=1.0)
        except OpenRouterError as e:
            await message.answer(f"❌ {e}")
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("LLM photo error")
            await message.answer(f"❌ Что-то пошло не так: {e}")
            return

        reply = _clean_reply(reply, girl.name)
        await memory.add_assistant(user_id, girl.id, reply)
        await _stream_reply(message, reply)
