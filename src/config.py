"""Конфигурация из переменных окружения."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")

    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        alias="OPENROUTER_MODEL",
    )

    allowed_user_ids_raw: str = Field("", alias="ALLOWED_USER_IDS")
    history_size: int = Field(20, alias="HISTORY_SIZE")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @property
    def allowed_user_ids(self) -> set[int]:
        raw = (self.allowed_user_ids_raw or "").strip()
        if not raw:
            return set()
        return {int(p) for p in raw.split(",") if p.strip().isdigit()}


settings = Settings()  # type: ignore[call-arg]
