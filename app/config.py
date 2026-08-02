from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    backend_api_base_url: str
    database_url: str
    request_timeout: int
    status_poll_interval: int
    default_user_credits: float
    available_numbers: tuple[str, ...]
    trunk_provider_name: str
    backend_host: str
    backend_port: int
    log_level: str



def _parse_numbers(raw_numbers: str) -> tuple[str, ...]:
    return tuple(number.strip() for number in raw_numbers.split(",") if number.strip())



def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        backend_api_base_url=os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:5000/api").rstrip("/"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///telegram_call_bot.db"),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "15")),
        status_poll_interval=int(os.getenv("STATUS_POLL_INTERVAL", "5")),
        default_user_credits=float(os.getenv("DEFAULT_USER_CREDITS", "10.0")),
        available_numbers=_parse_numbers(
            os.getenv("AVAILABLE_NUMBERS", "+12025550111,+12025550112,+12025550113")
        ),
        trunk_provider_name=os.getenv("TRUNK_PROVIDER_NAME", "example-trunk-provider"),
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("BACKEND_PORT", "5000")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
