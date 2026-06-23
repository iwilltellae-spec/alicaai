"""Whitelist по Telegram user_id."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.utils.logger import get_logger

logger = get_logger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: set[int]) -> None:
        self._allowed = allowed_ids
        if self._allowed:
            logger.info("Whitelist: %s", sorted(self._allowed))
        else:
            logger.warning("Whitelist ВЫКЛЮЧЕН — бот публичный.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._allowed:
            return await handler(event, data)
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)
        if event.from_user.id not in self._allowed:
            logger.info("Blocked: %s @%s", event.from_user.id, event.from_user.username)
            await event.answer("🚫 Этот бот приватный.")
            return None
        return await handler(event, data)
