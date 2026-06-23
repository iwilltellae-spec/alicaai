"""
Клиент OpenRouter с автоматическим fallback на резервные модели.

Если основная модель отвечает 429 (rate limit), 503 (нет capacity), или
другой временной ошибкой — клиент сам пробует следующую модель из цепочки.
Это делает бота устойчивым к перегрузкам бесплатных моделей.
"""
from __future__ import annotations

from typing import Optional

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# HTTP-коды, при которых имеет смысл пробовать следующую модель.
_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: str, models: list[str]) -> None:
        if not models:
            raise ValueError("Нужна хотя бы одна модель")
        self._api_key = api_key
        self._models = models
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=90),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
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
        """Перебирает модели по очереди, пока одна не ответит. Бросает только если ВСЕ упали."""
        last_error: Exception | None = None

        for idx, model in enumerate(self._models):
            try:
                reply = await self._chat_one(
                    model, messages, temperature=temperature, max_tokens=max_tokens
                )
                if idx > 0:
                    logger.info("✅ Fallback сработал на модели #%d: %s", idx, model)
                return reply
            except OpenRouterError as e:
                last_error = e
                # Если это не «временная» ошибка — нет смысла дёргать резервы (ключ битый и т.п.)
                if not getattr(e, "retryable", False):
                    raise
                logger.warning(
                    "Модель %s упала (%s) — пробую следующую…", model, e
                )

        # Все модели легли.
        raise OpenRouterError(
            f"Все модели сейчас недоступны (429/503). "
            f"Подожди 30 секунд и попробуй ещё раз. Последняя ошибка: {last_error}"
        )

    async def _chat_one(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        session = await self._get_session()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.3,
        }

        logger.info("OpenRouter: model=%s, messages=%d", model, len(messages))
        async with session.post(API_URL, json=payload) as resp:
            try:
                data = await resp.json()
            except Exception:  # noqa: BLE001
                data = {"error": {"message": await resp.text()}}

            if resp.status != 200:
                err = (data.get("error") or {}).get("message") or str(data)[:300]
                logger.error("OpenRouter %s on %s: %s", resp.status, model, err)
                exc = OpenRouterError(self._humanize(resp.status, err))
                exc.retryable = resp.status in _RETRYABLE_STATUSES or "rate" in err.lower()
                raise exc

            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error("Unexpected response from %s: %s", model, data)
                exc = OpenRouterError(f"Неожиданный ответ модели: {e}")
                exc.retryable = True
                raise exc

            if not content or not content.strip():
                exc = OpenRouterError("Пустой ответ от модели")
                exc.retryable = True
                raise exc

            return content.strip()

    @staticmethod
    def _humanize(status: int, msg: str) -> str:
        m = msg.lower()
        if status == 401:
            return "Неверный OpenRouter API key."
        if status == 402 or "credit" in m or "insufficient" in m:
            return "На OpenRouter закончились бесплатные кредиты. Подожди или пополни ($1-2 хватит надолго)."
        if status == 429 or "rate" in m:
            return "Лимит модели исчерпан. Подожди немного."
        if "moderat" in m or "flagged" in m:
            return "Модель отказала по своей модерации. Попробуй /reset и переформулируй."
        if status >= 500:
            return f"OpenRouter сейчас лежит ({status}). Попробуй через минуту."
        return f"Ошибка OpenRouter ({status}): {msg[:200]}"
