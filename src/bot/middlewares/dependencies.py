"""Прокидывает сервисы в хендлеры."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, llm: OpenRouterClient, memory: ChatMemory) -> None:
        self._llm = llm
        self._memory = memory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["llm"] = self._llm
        data["memory"] = self._memory
        return await handler(event, data)
