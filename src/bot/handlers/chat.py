"""Основной чат: текст и фото → LLM → разбитый на части ответ с задержками."""
from __future__ import annotations

import asyncio
import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.character.persona import build_system_prompt
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService
from src.utils.logger import get_logger
from src.utils.text import split_messages, strip_asterisks, typing_pause

logger = get_logger(__name__)
router = Router(name="chat")


# ---------------- helpers ----------------

async def _send_typing(message: Message, seconds: float) -> None:
    """Держим typing-индикатор И обязательно ждём seconds секунд."""
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
    """Шлём ответ кусками с реалистичной задержкой ПЕРЕД каждым."""
    parts = split_messages(full_text, max_parts=8)
    for part in parts:
        await _send_typing(message, typing_pause(part))
        await message.answer(part)


# ---------------- handlers ----------------

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

    # Если юзер в визарде — не реагируем как на чат.
    if await state.get_state() is not None:
        return

    if not memory.has_consent(user_id):
        await message.answer("Сначала /start и подтверди возраст.")
        return

    profile = storage.get(user_id)
    girl = profile.get_active_girl()

    memory.add_user(user_id, message.text)

    system = build_system_prompt(
        girl=girl,
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
        style="reply",
    )
    messages = [{"role": "system", "content": system}, *memory.get_history(user_id)]

    try:
        reply = await llm.chat(messages, temperature=1.0)
    except OpenRouterError as e:
        await message.answer(f"❌ {e}")
        bucket = memory._bucket(user_id)  # noqa: SLF001
        if bucket and bucket[-1]["role"] == "user":
            bucket.pop()
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("LLM error")
        await message.answer(f"❌ Что-то пошло не так: {e}")
        return

    reply = _clean_reply(reply, girl.name)
    memory.add_assistant(user_id, reply)
    await _stream_reply(message, reply)


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

    profile = storage.get(user_id)
    girl = profile.get_active_girl()

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    caption = message.caption or "(прислал фото без подписи)"

    memory.add_user(user_id, f"[фото] {caption}")

    system = build_system_prompt(
        girl=girl,
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
        style="photo",
    )
    user_content = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": file_url}},
    ]
    messages = [
        {"role": "system", "content": system},
        *memory.get_history(user_id)[:-1],
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
    memory.add_assistant(user_id, reply)
    await _stream_reply(message, reply)
