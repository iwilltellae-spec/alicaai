"""
Генерация фото через Gemini 2.5 Flash Image Preview (Nano Banana) на OpenRouter.

Использует отдельную модель, не трогает квоту основной чат-модели.
Если задан reference_file_id у девушки — Nano Banana получит это фото на вход
и сохранит черты лица/фигуры.

Возвращает либо bytes картинки, либо None если модель отказала / упала.
"""
from __future__ import annotations

import base64
import re
from typing import Optional

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)

API_URL = "https://neurorouters.com/api/v1/chat/completions"
# Nano Banana через NeuroRouters — бесплатно.
IMAGE_MODEL = "google/gemini-2.5-flash-image-preview:free"


# Стиль обязателен — иначе модель делает «студийный» рекламный шот.
STYLE_HINT = (
    "Selfie-style amateur phone photo, casual everyday snapshot, "
    "natural lighting, slight motion blur or imperfect framing, "
    "looks like a real iPhone selfie posted to Telegram. "
    "Not professional, not glamour, not studio. Realistic, candid, casual."
)


def build_scene_prompt(scene: str, girl_appearance: str) -> str:
    """Собирает финальный промпт для Nano Banana."""
    return (
        f"{STYLE_HINT}\n\n"
        f"Subject: {girl_appearance}\n\n"
        f"Scene: {scene}\n\n"
        "Keep the face and body of the subject consistent with the reference image. "
        "Only the scene, pose, expression, and background change. "
        "Photo must look like a casual amateur selfie, NOT a magazine photo."
    )


def appearance_summary(girl) -> str:
    """Короткое описание девушки для image-промпта (на английском — лучше работает)."""
    parts = [
        f"{girl.age}-year-old woman",
        girl.body_type,
        girl.height,
        f"{girl.hair_color} {girl.hair_length} hair",
        f"{girl.eyes} eyes",
    ]
    if girl.special:
        parts.append(", ".join(girl.special))
    parts.append(f"wearing: {girl.style_clothes}")
    return ", ".join(parts)


class ImageGenerator:
    def __init__(self, api_key: str, bot_token: str) -> None:
        self._api_key = api_key
        self._bot_token = bot_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
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

    async def _download_telegram_file(self, file_id: str) -> Optional[str]:
        """Скачивает Telegram-файл и возвращает data URL для отправки в LLM."""
        try:
            session = await self._get_session()
            # 1. Получаем путь файла.
            async with session.get(
                f"https://api.telegram.org/bot{self._bot_token}/getFile",
                params={"file_id": file_id},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                file_path = data.get("result", {}).get("file_path")
                if not file_path:
                    return None
            # 2. Скачиваем содержимое.
            async with session.get(
                f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}"
            ) as resp:
                if resp.status != 200:
                    return None
                content = await resp.read()
            b64 = base64.b64encode(content).decode("ascii")
            # Определяем mime по расширению.
            ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else "jpg"
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
            return f"data:{mime};base64,{b64}"
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог скачать референс из Telegram: %s", e)
            return None

    async def generate(
        self,
        scene: str,
        girl_appearance: str,
        reference_file_id: str = "",
    ) -> Optional[bytes]:
        """
        :param scene: словесное описание сцены (например, "сижу в кофейне с латте")
        :param girl_appearance: описание её внешности из анкеты
        :param reference_file_id: Telegram file_id для image-to-image
        :return: bytes картинки или None
        """
        prompt = build_scene_prompt(scene, girl_appearance)
        content: list[dict] = [{"type": "text", "text": prompt}]

        # Добавляем референс-картинку как input.
        if reference_file_id:
            data_url = await self._download_telegram_file(reference_file_id)
            if data_url:
                content.insert(0, {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
                logger.info("Image gen: с референсом (file_id=%s...)",
                            reference_file_id[:10])
            else:
                logger.warning("Референс не скачался — генерим без него")

        payload = {
            "model": IMAGE_MODEL,
            "modalities": ["text", "image"],
            "messages": [{"role": "user", "content": content}],
        }
        session = await self._get_session()
        try:
            async with session.post(API_URL, json=payload) as resp:
                # Сначала текст, чтобы корректно обработать non-JSON ответы.
                raw = await resp.text()
                try:
                    import json as _json
                    data = _json.loads(raw)
                except Exception:
                    data = None

                if resp.status != 200:
                    if isinstance(data, dict):
                        err = (data.get("error") or {})
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        msg = msg or str(data)[:300]
                    else:
                        msg = raw[:400]
                    logger.error("Nano Banana %s: %s", resp.status, msg)
                    return None

                if not isinstance(data, dict):
                    logger.error("Nano Banana: ответ не JSON. raw=%s", raw[:400])
                    return None

                # Парсим — изображение в choices[0].message.images[] или content.
                msg = (data.get("choices") or [{}])[0].get("message") or {}

                images = msg.get("images") or []
                for img in images:
                    if isinstance(img, dict):
                        url = (img.get("image_url") or {}).get("url") or img.get("url")
                    elif isinstance(img, str):
                        url = img
                    else:
                        url = None
                    if url:
                        decoded = _decode_data_url(url) or await self._download_url(url)
                        if decoded:
                            return decoded

                cont = msg.get("content")
                if isinstance(cont, list):
                    for part in cont:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") in ("image_url", "image", "output_image"):
                            url = (part.get("image_url") or {}).get("url") or part.get("url")
                            if url:
                                decoded = _decode_data_url(url) or await self._download_url(url)
                                if decoded:
                                    return decoded

                logger.warning("Nano Banana: в ответе нет картинки. data=%s",
                               str(data)[:500])
                return None
        except Exception as e:  # noqa: BLE001
            logger.exception("Nano Banana error: %s", e)
            return None

    async def _download_url(self, url: str) -> Optional[bytes]:
        """Скачивает картинку по обычному HTTP URL."""
        if not url.startswith("http"):
            return None
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог скачать картинку %s: %s", url[:80], e)
        return None


def _decode_data_url(url: str) -> Optional[bytes]:
    """data:image/png;base64,XXX → bytes."""
    if url.startswith("data:"):
        m = re.match(r"data:[^;]+;base64,(.+)", url)
        if m:
            try:
                return base64.b64decode(m.group(1))
            except Exception:  # noqa: BLE001
                return None
    return None
