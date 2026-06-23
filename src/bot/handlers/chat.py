"""Основной чат: текст и фото → LLM → разбитый на части ответ с задержками."""
from __future__ import annotations

import asyncio
import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from src.character.persona import build_system_prompt
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.services.weather import WeatherService
from src.utils.logger import get_logger
from src.utils.text import asterisks_to_italic, split_messages, typing_pause

logger = get_logger(__name__)
router = Router(name="chat")


# ---------------- helpers ----------------

async def _send_typing(message: Message, seconds: float) -> None:
    """Держим индикатор «печатает...» на нужное время."""
    elapsed = 0.0
    while elapsed < seconds:
        try:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:  # noqa: BLE001
            return
        chunk = min(4.0, seconds - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk


def _clean_reply(text: str) -> str:
    text = text.strip()
    for prefix in ("Алиса:", "Alice:", "Алиса —", "Алиса -"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"«':
        text = text[1:-1].strip()
    return text or "…"


async def _stream_reply_as_messages(
    message: Message,
    full_text: str,
) -> None:
    """
    Разбивает ответ на пачку коротких сообщений и шлёт их по очереди
    с реалистичными паузами и индикатором печати между ними.
    """
    parts = split_messages(full_text, max_parts=4)
    for i, part in enumerate(parts):
        # Перед каждой частью (кроме первой) — пауза + «печатает...»
        if i > 0:
            await _send_typing(message, typing_pause(part))
        formatted = asterisks_to_italic(part)
        await message.answer(formatted)


# ---------------- handlers ----------------

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message,
    bot: Bot,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
) -> None:
    user_id = message.from_user.id

    if not memory.has_consent(user_id):
        await message.answer("Нужно сначала подтвердить возраст. Нажми /start")
        return

    memory.add_user(user_id, message.text)

    system = build_system_prompt(
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
        style="reply",
    )
    messages = [{"role": "system", "content": system}, *memory.get_history(user_id)]

    # Стартовая пауза «увидела сообщение, начала печатать».
    initial_pause = min(2.5, 0.8 + len(message.text) * 0.02)
    await _send_typing(message, initial_pause)

    try:
        reply = await llm.chat(messages)
    except OpenRouterError as e:
        await message.answer(f"❌ {e}")
        # откатываем непрожитое сообщение из истории
        bucket = memory._bucket(user_id)  # noqa: SLF001
        if bucket and bucket[-1]["role"] == "user":
            bucket.pop()
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("LLM error")
        await message.answer(f"❌ Что-то пошло не так: {e}")
        return

    reply = _clean_reply(reply)
    memory.add_assistant(user_id, reply)
    await _stream_reply_as_messages(message, reply)


@router.message(F.photo)
async def handle_photo(
    message: Message,
    bot: Bot,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
) -> None:
    user_id = message.from_user.id

    if not memory.has_consent(user_id):
        await message.answer("Нужно сначала подтвердить возраст. Нажми /start")
        return

    # Берём фото в наибольшем разрешении.
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    caption = message.caption or "(прислал тебе фото без подписи)"

    # В историю кладём текстовую заметку (модель помнит что было фото).
    memory.add_user(user_id, f"[фото] {caption}")

    system = build_system_prompt(
        mood=memory.get_mood(user_id),
        weather=await weather.get(),
        now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3),
        style="photo",
    )

    # Multimodal-сообщение по OpenAI-формату (OpenRouter поддерживает).
    user_content = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": file_url}},
    ]
    messages = [
        {"role": "system", "content": system},
        *memory.get_history(user_id)[:-1],  # без последнего, заменим на multimodal
        {"role": "user", "content": user_content},
    ]

    await _send_typing(message, 2.0)

    try:
        reply = await llm.chat(messages)
    except OpenRouterError as e:
        await message.answer(f"❌ {e}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("LLM photo error")
        await message.answer(f"❌ Что-то пошло не так: {e}")
        return

    reply = _clean_reply(reply)
    memory.add_assistant(user_id, reply)
    await _stream_reply_as_messages(message, reply)
