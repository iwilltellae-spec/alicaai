"""
Память диалога: история сообщений + настроение + долгосрочные факты.

С БД (Database) — персистентно, переживает всё.
Без БД — in-memory (теряется при рестарте).

Долгосрочные факты — отдельная сущность. Раз в N сообщений отдельный LLM-запрос
извлекает «что я узнала о нём». Эти факты потом инжектятся в каждый системный промпт.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Optional

from src.services.db import Database
from src.services.mood import Mood, update_mood
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChatMemory:
    def __init__(self, max_messages: int, db: Optional[Database] = None) -> None:
        self._max = max_messages
        self._db = db

        # In-memory кеши (используем как кэш даже когда есть БД — быстрее).
        self._mood: dict[int, Mood] = {}
        self._last_user_activity: dict[int, float] = {}
        self._last_initiative: dict[int, float] = {}
        self._consented: set[int] = set()

        # Если БД нет — храним историю и факты в памяти.
        self._mem_history: dict[tuple[int, str], Deque[dict]] = defaultdict(
            lambda: deque(maxlen=max_messages)
        )
        self._mem_facts: dict[tuple[int, str], list[str]] = defaultdict(list)

    # ---------- consent ----------
    def has_consent(self, user_id: int) -> bool:
        return user_id in self._consented

    def grant_consent(self, user_id: int) -> None:
        self._consented.add(user_id)

    def all_consented_users(self) -> list[int]:
        return list(self._consented)

    # ---------- история ----------
    async def add_user(self, user_id: int, girl_id: str, text: str) -> None:
        self._mood[user_id] = update_mood(self.get_mood(user_id), text)
        self._last_user_activity[user_id] = time.time()
        if self._db:
            await self._db.add_message(user_id, girl_id, "user", text)
        else:
            self._mem_history[(user_id, girl_id)].append(
                {"role": "user", "content": text}
            )

    async def add_assistant(self, user_id: int, girl_id: str, text: str) -> None:
        if self._db:
            await self._db.add_message(user_id, girl_id, "assistant", text)
        else:
            self._mem_history[(user_id, girl_id)].append(
                {"role": "assistant", "content": text}
            )

    async def get_history(self, user_id: int, girl_id: str) -> list[dict]:
        if self._db:
            return await self._db.get_messages(user_id, girl_id, limit=self._max)
        return list(self._mem_history[(user_id, girl_id)])

    async def reset(self, user_id: int, girl_id: str = "") -> None:
        """Если girl_id пустой — стираем для всех её, иначе только конкретной."""
        self._mood.pop(user_id, None)
        if not girl_id:
            # Очищаем всё что есть в кэше
            for key in list(self._mem_history.keys()):
                if key[0] == user_id:
                    del self._mem_history[key]
            for key in list(self._mem_facts.keys()):
                if key[0] == user_id:
                    del self._mem_facts[key]
            return
        if self._db:
            await self._db.clear_messages(user_id, girl_id)
            await self._db.clear_facts(user_id, girl_id)
        self._mem_history.pop((user_id, girl_id), None)
        self._mem_facts.pop((user_id, girl_id), None)

    async def message_count(self, user_id: int, girl_id: str) -> int:
        if self._db:
            return await self._db.count_messages(user_id, girl_id)
        return len(self._mem_history[(user_id, girl_id)])

    # ---------- факты (долгосрочная память) ----------
    async def add_fact(self, user_id: int, girl_id: str, fact: str) -> None:
        if self._db:
            await self._db.add_fact(user_id, girl_id, fact)
        else:
            self._mem_facts[(user_id, girl_id)].append(fact)

    async def get_facts(self, user_id: int, girl_id: str) -> list[str]:
        if self._db:
            return await self._db.get_facts(user_id, girl_id, limit=30)
        return list(self._mem_facts[(user_id, girl_id)])[-30:]

    # ---------- настроение ----------
    def get_mood(self, user_id: int) -> Mood:
        return self._mood.get(user_id, Mood())

    # ---------- активность ----------
    def get_last_activity(self, user_id: int) -> float:
        return self._last_user_activity.get(user_id, 0.0)

    def get_last_initiative(self, user_id: int) -> float:
        return self._last_initiative.get(user_id, 0.0)

    def mark_initiative(self, user_id: int) -> None:
        self._last_initiative[user_id] = time.time()
