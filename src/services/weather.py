"""
Погода через Open-Meteo (https://open-meteo.com) — бесплатно, без API-ключа.

Кэшируем на 30 минут, чтобы не дёргать API на каждое сообщение.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)


# Питер по умолчанию (Алиса оттуда).
DEFAULT_LAT = 59.94
DEFAULT_LON = 30.31
CITY_NAME = "Питер"

# Open-Meteo WMO weather codes → человеческое описание на русском.
_WMO_RU = {
    0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "изморозь",
    51: "мелкая морось", 53: "морось", 55: "сильная морось",
    61: "слабый дождь", 63: "дождь", 65: "сильный дождь",
    66: "ледяной дождь", 67: "сильный ледяной дождь",
    71: "слабый снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "ливень", 81: "сильный ливень", 82: "очень сильный ливень",
    85: "снегопад", 86: "сильный снегопад",
    95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}


@dataclass(slots=True)
class Weather:
    temp_c: float
    description: str
    city: str


class WeatherService:
    def __init__(self, cache_ttl: int = 1800) -> None:
        self._cache_ttl = cache_ttl
        self._cache: Optional[Weather] = None
        self._cache_time: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self) -> Optional[Weather]:
        # Кэш свежий — возвращаем.
        now = time.monotonic()
        if self._cache and now - self._cache_time < self._cache_ttl:
            return self._cache

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}"
            "&current=temperature_2m,weather_code"
            "&timezone=Europe/Moscow"
        )
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Open-Meteo %s", resp.status)
                    return self._cache  # вернём старое если есть
                data = await resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("Open-Meteo fail: %s", e)
            return self._cache

        current = data.get("current") or {}
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None or code is None:
            return self._cache

        self._cache = Weather(
            temp_c=round(float(temp), 1),
            description=_WMO_RU.get(int(code), "обычная погода"),
            city=CITY_NAME,
        )
        self._cache_time = now
        logger.info("Weather: %s °C, %s", self._cache.temp_c, self._cache.description)
        return self._cache
