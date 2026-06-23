"""Регистрация всех роутеров. Порядок важен — выше = выше приоритет."""
from __future__ import annotations

from aiogram import Router

from . import age_gate, commands, menu, wizard, chat


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(age_gate.router)
    root.include_router(wizard.router)   # FSM — должен быть до общих
    root.include_router(menu.router)
    root.include_router(commands.router)
    root.include_router(chat.router)     # самый общий (любой текст) — в конце
    return root
