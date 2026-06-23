"""Служебные команды: /help, /reset, /who."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.services.memory import ChatMemory

router = Router(name="commands")


HELP = (
    "<b>💬 Алиса — твой собеседник</b>\n\n"
    "Просто пиши ей сообщения, как живому человеку.\n\n"
    "<b>Команды</b>\n"
    "/reset — начать диалог с нуля (забудет всё)\n"
    "/who — кто такая Алиса\n"
    "/help — это сообщение"
)

WHO = (
    "<b>Алиса, 22</b>\n"
    "<i>Питер. Свитера, колготки в сетку, родинка над губой.</i>\n\n"
    "Ласковая, игривая, немного дерзкая. Любит подкалывать, "
    "может застесняться, а через секунду сказать что-нибудь откровенное.\n\n"
    "Для тебя она — твоя девушка. Помнит последние "
    f"{settings.history_size} сообщений в чате."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("who"))
async def cmd_who(message: Message) -> None:
    await message.answer(WHO)


@router.message(Command("reset"))
async def cmd_reset(message: Message, memory: ChatMemory) -> None:
    memory.reset(message.from_user.id)
    await message.answer("♻️ Я всё забыла. Привет, незнакомец 😏")
