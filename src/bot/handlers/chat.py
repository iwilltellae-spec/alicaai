"""Основной чат-обработчик: текст → LLM → ответ."""
from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from src.character.persona import get_system_prompt
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="chat")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(
    message: Message,
    llm: OpenRouterClient,
    memory: ChatMemory,
) -> None:
    user_id = message.from_user.id

    # 1. Проверка 18+ согласия.
    if not memory.has_consent(user_id):
        await message.answer(
            "Нужно сначала подтвердить возраст. Нажми /start"
        )
        return

    # 2. Складываем фразу пользователя в историю.
    memory.add_user(user_id, message.text)

    # 3. Собираем messages для LLM: system + вся история.
    messages = [
        {"role": "system", "content": get_system_prompt()},
        *memory.get_history(user_id),
    ]

    # 4. Имитируем «печатает...» пока ждём ответ от LLM.
    typing_task = asyncio.create_task(_show_typing(message))

    try:
        reply = await llm.chat(messages)
    except OpenRouterError as e:
        typing_task.cancel()
        await message.answer(f"❌ {e}")
        # Откатываем добавленное сообщение, чтобы не «протухло» в истории.
        history = memory.get_history(user_id)
        if history and history[-1]["role"] == "user":
            memory._bucket(user_id).pop()  # noqa: SLF001
        return
    except Exception as e:  # noqa: BLE001
        typing_task.cancel()
        logger.exception("LLM unexpected error")
        await message.answer(f"❌ Что-то пошло не так: {e}")
        return
    finally:
        typing_task.cancel()

    # 5. Сохраняем и отправляем.
    reply = _clean_reply(reply)
    memory.add_assistant(user_id, reply)
    await message.answer(reply)


async def _show_typing(message: Message) -> None:
    """Постоянно держим индикатор 'печатает...' пока ждём LLM."""
    try:
        while True:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


def _clean_reply(text: str) -> str:
    """Минимальная очистка ответа от типичных артефактов LLM."""
    text = text.strip()
    # Иногда модели префиксят ответ "Алиса:" — убираем.
    for prefix in ("Алиса:", "Alice:", "Алиса —", "Алиса -"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    # Убираем обёртывающие кавычки, если весь ответ в них.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"«':
        text = text[1:-1].strip()
    return text or "…"
