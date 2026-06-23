"""Регистрация роутеров. Порядок: специфичные → общие."""
from __future__ import annotations

from aiogram import Router

from . import age_gate, commands, menu, photo_request, wizard, chat


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(age_gate.router)
    root.include_router(wizard.router)        # FSM
    root.include_router(photo_request.router) # FSM + специфичный триггер
    root.include_router(menu.router)
    root.include_router(commands.router)
    root.include_router(chat.router)          # всеядный — в конец
    return root
