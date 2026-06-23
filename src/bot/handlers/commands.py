"""Базовые служебные команды."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.services.memory import ChatMemory

router = Router(name="commands")


@router.message(Command("reset"))
async def cmd_reset(message: Message, memory: ChatMemory) -> None:
    memory.reset(message.from_user.id)
    await message.answer("♻️ Память стёрта. Начинаем с чистого листа.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>💬 Бот-собеседник</b>\n\n"
        "Просто пиши активной девушке.\n\n"
        "<b>Команды</b>\n"
        "/menu — главное меню\n"
        "/reset — стереть память диалога\n"
        "/help — это сообщение"
    )
