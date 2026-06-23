"""Меню команд бота (кнопка ☰ слева от ввода)."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands


COMMANDS: list[BotCommand] = [
    BotCommand(command="who",   description="👤 Кто такая Алиса"),
    BotCommand(command="reset", description="♻️ Начать с нуля"),
    BotCommand(command="help",  description="ℹ️ Помощь"),
]


async def setup_menu(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
