"""
Профиль пользователя: баланс, список девушек, активная.

Хранение в /tmp/profiles.json — переживает обычные перезапуски сервиса
на Render. При новом деплое (push в GitHub) сбрасывается. Это компромисс
ради "без БД".
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.character.girl import Girl, default_girl
from src.utils.logger import get_logger

logger = get_logger(__name__)

_FILE = Path("/tmp/profiles.json")
_LOCK = threading.Lock()


# Цены / стартовые значения
START_BALANCE = 100
COST_NEW_GIRL = 50
DAILY_BONUS = 20
MAX_GIRLS = 8  # технический предел чтоб не разнесло


@dataclass
class Profile:
    user_id: int
    balance: int = START_BALANCE
    last_daily_bonus_ts: float = 0.0
    girls: dict[str, dict] = field(default_factory=dict)  # girl_id → dict
    active_girl_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            user_id=d["user_id"],
            balance=d.get("balance", START_BALANCE),
            last_daily_bonus_ts=d.get("last_daily_bonus_ts", 0.0),
            girls=d.get("girls", {}),
            active_girl_id=d.get("active_girl_id", ""),
        )

    # ----- girls -----
    def get_active_girl(self) -> Girl:
        if self.active_girl_id and self.active_girl_id in self.girls:
            return Girl.from_dict(self.girls[self.active_girl_id])
        # fallback к дефолтной Алисе
        g = default_girl()
        if g.id not in self.girls:
            self.girls[g.id] = g.to_dict()
        self.active_girl_id = g.id
        return g

    def list_girls(self) -> list[Girl]:
        return [Girl.from_dict(d) for d in self.girls.values()]

    def save_girl(self, girl: Girl) -> None:
        self.girls[girl.id] = girl.to_dict()

    def set_active(self, girl_id: str) -> bool:
        if girl_id in self.girls:
            self.active_girl_id = girl_id
            return True
        return False

    def remove_girl(self, girl_id: str) -> bool:
        # Дефолтную не удаляем.
        if girl_id == "default_alisa":
            return False
        if girl_id in self.girls:
            del self.girls[girl_id]
            if self.active_girl_id == girl_id:
                self.active_girl_id = "default_alisa"
                self.get_active_girl()  # гарантируем что дефолтная есть
            return True
        return False

    # ----- balance -----
    def claim_daily_bonus(self) -> int:
        """Возвращает сколько начислено (0 если ещё рано)."""
        now = time.time()
        if now - self.last_daily_bonus_ts < 23 * 3600:
            return 0
        self.last_daily_bonus_ts = now
        self.balance += DAILY_BONUS
        return DAILY_BONUS


class ProfileStorage:
    def __init__(self) -> None:
        self._profiles: dict[int, Profile] = {}
        self._load()

    # ---- IO ----
    def _load(self) -> None:
        if not _FILE.exists():
            logger.info("profiles.json не найден, начинаем с пустого хранилища")
            return
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            for uid_str, p in data.items():
                self._profiles[int(uid_str)] = Profile.from_dict(p)
            logger.info("Загружено профилей: %d", len(self._profiles))
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог прочитать профили: %s", e)

    def _save(self) -> None:
        try:
            data = {str(uid): p.to_dict() for uid, p in self._profiles.items()}
            _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог сохранить профили: %s", e)

    # ---- API ----
    def get(self, user_id: int) -> Profile:
        with _LOCK:
            if user_id not in self._profiles:
                p = Profile(user_id=user_id)
                p.get_active_girl()  # инициализирует дефолтную Алису
                self._profiles[user_id] = p
                self._save()
            return self._profiles[user_id]

    def commit(self, profile: Profile) -> None:
        with _LOCK:
            self._profiles[profile.user_id] = profile
            self._save()
