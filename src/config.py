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
    # Резервные модели через запятую — если основная вернёт 429/503,
    # бот по очереди пробует их. Оставь пустым чтобы отключить fallback.
    openrouter_fallbacks_raw: str = Field(
        "nousresearch/hermes-3-llama-3.1-405b:free,"
        "qwen/qwen3-next-80b-a3b-instruct:free,"
        "meta-llama/llama-3.3-70b-instruct:free",
        alias="OPENROUTER_FALLBACKS",
    )

    allowed_user_ids_raw: str = Field("", alias="ALLOWED_USER_IDS")
    history_size: int = Field(40, alias="HISTORY_SIZE")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # БД (Neon Postgres). Если пусто — работает в in-memory режиме (как раньше).
    database_url: str = Field("", alias="DATABASE_URL")

    @property
    def allowed_user_ids(self) -> set[int]:
        raw = (self.allowed_user_ids_raw or "").strip()
        if not raw:
            return set()
        return {int(p) for p in raw.split(",") if p.strip().isdigit()}

    @property
    def openrouter_models_chain(self) -> list[str]:
        """Основная модель + резервные, в порядке попыток."""
        chain = [self.openrouter_model]
        for m in (self.openrouter_fallbacks_raw or "").split(","):
            m = m.strip()
            if m and m not in chain:
                chain.append(m)
        return chain


settings = Settings()  # type: ignore[call-arg]
