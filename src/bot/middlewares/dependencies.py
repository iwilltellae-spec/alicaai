"""Прокидывает сервисы в хендлеры."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services.image_gen import ImageGenerator
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService


class DependenciesMiddleware(BaseMiddleware):
    def __init__(
        self,
        llm: OpenRouterClient,
        memory: ChatMemory,
        weather: WeatherService,
        storage: ProfileStorage,
        image_gen: ImageGenerator,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._weather = weather
        self._storage = storage
        self._image_gen = image_gen

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["llm"] = self._llm
        data["memory"] = self._memory
        data["weather"] = self._weather
        data["storage"] = self._storage
        data["image_gen"] = self._image_gen
        return await handler(event, data)
