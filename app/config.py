from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str
    admin_telegram_ids: List[int] = []

    # Database
    database_url: str = "sqlite+aiosqlite:///smsbot.db"  # Override with PostgreSQL in production

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Encryption key (Fernet 32-byte base64 key)
    encryption_key: str

    # Timezone
    app_timezone: str = "America/Detroit"

    # Rate limits
    daily_message_limit: int = 250
    hourly_message_limit: int = 50
    minute_message_limit: int = 5

    # Logging
    log_level: str = "INFO"

    # Web admin
    web_admin_host: str = "0.0.0.0"
    web_admin_port: int = 8080
    web_admin_secret: str = "change-me-in-production"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> List[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    @field_validator("log_level")
    @classmethod
    def upper_log_level(cls, v: str) -> str:
        return v.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
