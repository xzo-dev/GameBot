from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    owner_id: int = 0
    backup_channel_id: int = 0
    database_url: str = "sqlite+aiosqlite:///./gamehub.db"
    frontend_url: str = "http://localhost:5173"
    webhook_secret: str = ""
    secret_key: str = ""
    public_base_url: str = ""
    session_ttl_hours: int = 720
    admin_ids: str = ""
    dev_mode: bool = False

    @property
    def session_key(self) -> bytes:
        raw = self.secret_key or f"{self.bot_token}:gamehub-session"
        return hashlib.sha256(raw.encode()).digest()

    @property
    def admins(self) -> set[int]:
        ids = {self.owner_id} if self.owner_id else set()
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
