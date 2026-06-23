"""
In-memory история диалога + флаг 18+ согласия.

Не персистентно: при рестарте Render контейнер пересоздаётся → история теряется.
Это сознательное решение (без БД, как договорились). Для долгосрочной памяти
надо подключать Postgres / SQLite на диске.
"""
from __future__ import annotations

from collections import deque
from typing import Deque


class ChatMemory:
    def __init__(self, max_messages: int) -> None:
        self._max = max_messages
        self._history: dict[int, Deque[dict]] = {}
        self._consented: set[int] = set()

    # ---------- 18+ согласие ----------

    def has_consent(self, user_id: int) -> bool:
        return user_id in self._consented

    def grant_consent(self, user_id: int) -> None:
        self._consented.add(user_id)

    def revoke_consent(self, user_id: int) -> None:
        self._consented.discard(user_id)

    # ---------- история ----------

    def _bucket(self, user_id: int) -> Deque[dict]:
        if user_id not in self._history:
            self._history[user_id] = deque(maxlen=self._max)
        return self._history[user_id]

    def add_user(self, user_id: int, text: str) -> None:
        self._bucket(user_id).append({"role": "user", "content": text})

    def add_assistant(self, user_id: int, text: str) -> None:
        self._bucket(user_id).append({"role": "assistant", "content": text})

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._bucket(user_id))

    def reset(self, user_id: int) -> None:
        self._history.pop(user_id, None)

    def message_count(self, user_id: int) -> int:
        return len(self._bucket(user_id))
