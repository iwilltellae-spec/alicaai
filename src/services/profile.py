"""
Профиль пользователя: баланс, список девушек, активная.

Backend выбирается по наличию settings.database_url:
- если есть DATABASE_URL → персистентно в Postgres
- если нет → in-memory (как раньше) с сохранением в /tmp/profiles.json
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from src.character.girl import Girl, default_girl
from src.services.db import Database
from src.utils.logger import get_logger

logger = get_logger(__name__)

_FILE = Path("/tmp/profiles.json")

START_BALANCE = 100
COST_NEW_GIRL = 50
DAILY_BONUS = 20
MAX_GIRLS = 8


@dataclass
class Profile:
    user_id: int
    balance: int = START_BALANCE
    last_daily_bonus_ts: float = 0.0
    active_girl_id: str = ""
    consented: bool = False
    girls: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            user_id=d["user_id"],
            balance=d.get("balance", START_BALANCE),
            last_daily_bonus_ts=d.get("last_daily_bonus_ts", 0.0),
            active_girl_id=d.get("active_girl_id", ""),
            consented=d.get("consented", False),
            girls=d.get("girls", {}),
        )

    def get_active_girl(self) -> Girl:
        if self.active_girl_id and self.active_girl_id in self.girls:
            return Girl.from_dict(self.girls[self.active_girl_id])
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
        if girl_id == "default_alisa":
            return False
        if girl_id in self.girls:
            del self.girls[girl_id]
            if self.active_girl_id == girl_id:
                self.active_girl_id = "default_alisa"
                self.get_active_girl()
            return True
        return False

    def claim_daily_bonus(self) -> int:
        now = time.time()
        if now - self.last_daily_bonus_ts < 23 * 3600:
            return 0
        self.last_daily_bonus_ts = now
        self.balance += DAILY_BONUS
        return DAILY_BONUS


class ProfileStorage:
    """Асинхронный фасад поверх БД или /tmp/profiles.json."""

    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db
        # in-memory кеш — чтобы не дёргать БД на каждый чих
        self._cache: dict[int, Profile] = {}
        self._loaded = False

    async def init(self) -> None:
        if self._db is None:
            self._load_file()
            self._loaded = True
            logger.info("ProfileStorage: file backend (/tmp/profiles.json)")
        else:
            logger.info("ProfileStorage: postgres backend")

    # ---- file backend ----
    def _load_file(self) -> None:
        if not _FILE.exists():
            return
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            for uid_str, p in data.items():
                self._cache[int(uid_str)] = Profile.from_dict(p)
            logger.info("Загружено профилей из файла: %d", len(self._cache))
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог прочитать profiles.json: %s", e)

    def _save_file(self) -> None:
        try:
            data = {str(uid): p.to_dict() for uid, p in self._cache.items()}
            _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("Не смог сохранить profiles.json: %s", e)

    # ---- public API ----
    async def get(self, user_id: int) -> Profile:
        if user_id in self._cache:
            return self._cache[user_id]

        if self._db:
            data = await self._db.get_profile(user_id)
            if data:
                profile = Profile(
                    user_id=data["user_id"],
                    balance=data["balance"],
                    last_daily_bonus_ts=data["last_daily_bonus_ts"] or 0.0,
                    active_girl_id=data["active_girl_id"] or "",
                    consented=data["consented"] or False,
                )
                girls_data = await self._db.list_girls(user_id)
                profile.girls = {g["id"]: g for g in girls_data}
                if not profile.girls:
                    # Гарантируем дефолтную Алису.
                    profile.get_active_girl()
                    await self._db.upsert_girl(
                        user_id, "default_alisa", profile.girls["default_alisa"],
                    )
                self._cache[user_id] = profile
                return profile

        # Не нашли в БД (или БД нет) — создаём новый.
        profile = Profile(user_id=user_id)
        profile.get_active_girl()  # создаёт default_alisa
        self._cache[user_id] = profile
        await self.commit(profile)
        return profile

    async def commit(self, profile: Profile) -> None:
        self._cache[profile.user_id] = profile
        if self._db:
            await self._db.upsert_profile(
                profile.user_id,
                balance=profile.balance,
                last_daily_bonus_ts=profile.last_daily_bonus_ts,
                active_girl_id=profile.active_girl_id,
                consented=profile.consented,
            )
            # Синхронизируем девушек.
            for gid, gdata in profile.girls.items():
                await self._db.upsert_girl(profile.user_id, gid, gdata)
        else:
            self._save_file()

    async def remove_girl(self, profile: Profile, girl_id: str) -> bool:
        ok = profile.remove_girl(girl_id)
        if ok and self._db:
            await self._db.delete_girl(profile.user_id, girl_id)
        await self.commit(profile)
        return ok
