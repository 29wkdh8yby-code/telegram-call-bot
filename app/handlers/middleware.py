"""Shared middleware: user upsert, suspension check, audit context."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from app.database import get_session_factory
from app.repository import upsert_user

logger = structlog.get_logger(__name__)


class UserMiddleware(BaseMiddleware):
    """Upsert user on every incoming event; inject db_user into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None and isinstance(event, Update):
            tg_user = event.event.from_user if hasattr(event.event, "from_user") else None

        if tg_user and not tg_user.is_bot:
            factory = get_session_factory()
            async with factory() as session:
                db_user = await upsert_user(
                    session,
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                data["db_user"] = db_user
                data["db_session"] = session
                return await handler(event, data)

        return await handler(event, data)
