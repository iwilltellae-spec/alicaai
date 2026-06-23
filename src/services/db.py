"""
Слой работы с Postgres (Neon бесплатный).

Хранит:
- profiles: баланс, активная девушка
- girls: все девушки пользователя (JSONB)
- messages: история диалогов (по girl_id)
- facts: что Алиса узнала о пользователе (имя, работа, и т.д.)
"""
from __future__ import annotations

import json
import ssl
from typing import Optional

import asyncpg

from src.utils.logger import get_logger

logger = get_logger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    user_id BIGINT PRIMARY KEY,
    balance INT NOT NULL DEFAULT 100,
    last_daily_bonus_ts DOUBLE PRECISION DEFAULT 0,
    active_girl_id TEXT,
    consented BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS girls (
    girl_id TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (girl_id, user_id)
);
CREATE INDEX IF NOT EXISTS girls_user_idx ON girls(user_id);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    girl_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS messages_user_girl_idx ON messages(user_id, girl_id, id DESC);

CREATE TABLE IF NOT EXISTS facts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    girl_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS facts_user_girl_idx ON facts(user_id, girl_id);
"""


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        # Neon требует SSL.
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=1,
            max_size=5,
            ssl=ssl_ctx,
            command_timeout=30,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("БД подключена и схема создана.")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # ---------- profiles ----------
    async def get_profile(self, user_id: int) -> Optional[dict]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow(
                "SELECT * FROM profiles WHERE user_id=$1", user_id
            )
            return dict(row) if row else None

    async def upsert_profile(self, user_id: int, *, balance: int,
                             last_daily_bonus_ts: float,
                             active_girl_id: str, consented: bool) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute("""
                INSERT INTO profiles
                  (user_id, balance, last_daily_bonus_ts, active_girl_id, consented)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                  balance = EXCLUDED.balance,
                  last_daily_bonus_ts = EXCLUDED.last_daily_bonus_ts,
                  active_girl_id = EXCLUDED.active_girl_id,
                  consented = EXCLUDED.consented
            """, user_id, balance, last_daily_bonus_ts, active_girl_id, consented)

    # ---------- girls ----------
    async def upsert_girl(self, user_id: int, girl_id: str, data: dict) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute("""
                INSERT INTO girls (girl_id, user_id, data, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (girl_id, user_id) DO UPDATE SET
                  data = EXCLUDED.data,
                  updated_at = NOW()
            """, girl_id, user_id, json.dumps(data))

    async def list_girls(self, user_id: int) -> list[dict]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch(
                "SELECT data FROM girls WHERE user_id=$1 ORDER BY created_at",
                user_id,
            )
            return [json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
                    for r in rows]

    async def get_girl(self, user_id: int, girl_id: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow(
                "SELECT data FROM girls WHERE user_id=$1 AND girl_id=$2",
                user_id, girl_id,
            )
            if not row:
                return None
            data = row["data"]
            return json.loads(data) if isinstance(data, str) else data

    async def delete_girl(self, user_id: int, girl_id: str) -> bool:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            res = await conn.execute(
                "DELETE FROM girls WHERE user_id=$1 AND girl_id=$2",
                user_id, girl_id,
            )
            return res.endswith("1")

    # ---------- messages ----------
    async def add_message(self, user_id: int, girl_id: str,
                          role: str, content: str) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute("""
                INSERT INTO messages (user_id, girl_id, role, content)
                VALUES ($1, $2, $3, $4)
            """, user_id, girl_id, role, content)

    async def get_messages(self, user_id: int, girl_id: str,
                           limit: int = 40) -> list[dict]:
        """Возвращает последние N сообщений в хронологическом порядке."""
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch("""
                SELECT role, content FROM messages
                WHERE user_id=$1 AND girl_id=$2
                ORDER BY id DESC LIMIT $3
            """, user_id, girl_id, limit)
        return [{"role": r["role"], "content": r["content"]}
                for r in reversed(rows)]

    async def clear_messages(self, user_id: int, girl_id: str) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "DELETE FROM messages WHERE user_id=$1 AND girl_id=$2",
                user_id, girl_id,
            )

    async def count_messages(self, user_id: int, girl_id: str) -> int:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            return await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE user_id=$1 AND girl_id=$2",
                user_id, girl_id,
            ) or 0

    # ---------- facts ----------
    async def add_fact(self, user_id: int, girl_id: str, fact: str) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute("""
                INSERT INTO facts (user_id, girl_id, fact) VALUES ($1, $2, $3)
            """, user_id, girl_id, fact[:500])

    async def get_facts(self, user_id: int, girl_id: str,
                        limit: int = 30) -> list[str]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch("""
                SELECT fact FROM facts
                WHERE user_id=$1 AND girl_id=$2
                ORDER BY id DESC LIMIT $3
            """, user_id, girl_id, limit)
        return [r["fact"] for r in reversed(rows)]

    async def clear_facts(self, user_id: int, girl_id: str) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "DELETE FROM facts WHERE user_id=$1 AND girl_id=$2",
                user_id, girl_id,
            )

    async def all_user_ids(self) -> list[int]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch(
                "SELECT user_id FROM profiles WHERE consented=TRUE"
            )
        return [r["user_id"] for r in rows]
