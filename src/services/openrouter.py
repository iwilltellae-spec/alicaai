"""
Клиент OpenRouter (OpenAI-совместимый Chat Completions API).

Документация: https://openrouter.ai/docs
"""
from __future__ import annotations

from typing import Optional

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=90),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    # Заголовки опциональные, но OpenRouter их любит для аналитики.
                    "HTTP-Referer": "https://t.me/character_chat_bot",
                    "X-Title": "Character Chat Bot",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.9,
        max_tokens: int = 600,
    ) -> str:
        """
        :param messages: список вида [{"role": "system"|"user"|"assistant", "content": "..."}]
        :return: текст ответа модели.
        """
        session = await self._get_session()
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Чуть-чуть «креативности» поверх temperature.
            "top_p": 0.95,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.3,
        }

        logger.info(
            "OpenRouter request: model=%s, messages=%d", self._model, len(messages)
        )
        async with session.post(API_URL, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                err = (data.get("error") or {}).get("message") or str(data)[:300]
                logger.error("OpenRouter %s: %s", resp.status, err)
                raise OpenRouterError(self._humanize(resp.status, err))

            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error("Unexpected OpenRouter response: %s", data)
                raise OpenRouterError(f"Неожиданный ответ от модели: {e}")
            return content.strip()

    @staticmethod
    def _humanize(status: int, msg: str) -> str:
        m = msg.lower()
        if status == 401:
            return "Неверный OpenRouter API key."
        if status == 402 or "credit" in m or "insufficient" in m:
            return "На OpenRouter закончились бесплатные кредиты. Подожди или пополни счёт ($1-2 хватит надолго)."
        if status == 429 or "rate" in m:
            return "Слишком много запросов к модели. Подожди 10-30 секунд."
        if "moderat" in m or "flagged" in m:
            return "Модель отказала по своей внутренней модерации. Попробуй переформулировать или /reset."
        if status >= 500:
            return f"OpenRouter сейчас лежит ({status}). Попробуй через минуту."
        return f"Ошибка OpenRouter ({status}): {msg[:200]}"
