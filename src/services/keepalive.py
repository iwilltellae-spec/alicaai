"""Самопинг для бесплатного Render Web Service."""
from __future__ import annotations

import asyncio
import os

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)
PING_INTERVAL = 10 * 60


async def keepalive_loop() -> None:
    base = os.environ.get("RENDER_EXTERNAL_URL")
    if not base:
        logger.info("RENDER_EXTERNAL_URL не задан — keep-alive выключен.")
        return
    url = base.rstrip("/") + "/healthz"
    logger.info("Keep-alive: %s каждые %ds", url, PING_INTERVAL)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        while True:
            try:
                async with s.get(url) as r:
                    logger.debug("ping: %s", r.status)
            except Exception as e:  # noqa: BLE001
                logger.warning("ping failed: %s", e)
            await asyncio.sleep(PING_INTERVAL)
