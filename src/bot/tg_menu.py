"""Меню команд Telegram (синяя кнопка ☰ слева от ввода)."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands


COMMANDS: list[BotCommand] = [
    BotCommand(command="menu",  description="🏠 Главное меню"),
    BotCommand(command="reset", description="♻️ Стереть память диалога"),
    BotCommand(command="help",  description="ℹ️ Помощь"),
]


async def setup_menu(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
