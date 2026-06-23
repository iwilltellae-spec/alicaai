"""In-memory история + 18+ согласие + настроение + время последней активности."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque

from src.services.mood import Mood, update_mood


class ChatMemory:
    def __init__(self, max_messages: int) -> None:
        self._max = max_messages
        self._history: dict[int, Deque[dict]] = {}
        self._consented: set[int] = set()
        self._mood: dict[int, Mood] = {}
        self._last_user_activity: dict[int, float] = {}
        self._last_initiative: dict[int, float] = {}

    # ---------- consent ----------
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
        self._mood[user_id] = update_mood(self.get_mood(user_id), text)
        self._last_user_activity[user_id] = time.time()

    def add_assistant(self, user_id: int, text: str) -> None:
        self._bucket(user_id).append({"role": "assistant", "content": text})

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._bucket(user_id))

    def reset(self, user_id: int) -> None:
        self._history.pop(user_id, None)
        self._mood.pop(user_id, None)

    def message_count(self, user_id: int) -> int:
        return len(self._bucket(user_id))

    # ---------- mood ----------
    def get_mood(self, user_id: int) -> Mood:
        return self._mood.get(user_id, Mood())

    # ---------- активность ----------
    def get_last_activity(self, user_id: int) -> float:
        return self._last_user_activity.get(user_id, 0.0)

    def get_last_initiative(self, user_id: int) -> float:
        return self._last_initiative.get(user_id, 0.0)

    def mark_initiative(self, user_id: int) -> None:
        self._last_initiative[user_id] = time.time()

    def all_consented_users(self) -> list[int]:
        return list(self._consented)
