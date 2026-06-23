"""Регистрация всех роутеров."""
from __future__ import annotations

from aiogram import Router

from . import age_gate, commands, chat


def get_root_router() -> Router:
    root = Router(name="root")
    # Порядок важен: age_gate ловит колбэки подтверждения, потом команды, потом чат.
    root.include_router(age_gate.router)
    root.include_router(commands.router)
    root.include_router(chat.router)
    return root
