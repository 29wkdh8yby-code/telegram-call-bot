"""Main Telegram bot application using aiogram 3."""
from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.config import get_settings
from app.handlers import admin_handler, menu, recipient_handler, send_handler, settings_handler, smtp_handler
from app.handlers.middleware import UserMiddleware
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Register middleware
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    # Register routers
    dp.include_router(menu.router)
    dp.include_router(smtp_handler.router)
    dp.include_router(recipient_handler.router)
    dp.include_router(send_handler.router)
    dp.include_router(settings_handler.router)
    dp.include_router(admin_handler.router)

    logger.info("bot_starting")
    await dp.start_polling(bot, drop_pending_updates=True)


def run() -> None:
    asyncio.run(main())
