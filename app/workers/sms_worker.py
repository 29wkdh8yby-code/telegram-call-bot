"""ARQ background worker for sending SMS messages."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog
from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session_factory
from app.models import MessageDelivery, MessageStatus, SmtpAccount
from app.repository import (
    get_smtp_account,
    mark_delivery_failed,
    mark_delivery_sent,
)
from app.services.smtp_service import smtp_config_from_account, send_sms_via_smtp

logger = structlog.get_logger(__name__)

OPTOUT_FOOTER = "\n\nReply STOP to opt out, or contact the sender to unsubscribe."


async def send_delivery(ctx: dict, delivery_id: int, smtp_account_id: int) -> dict[str, Any]:
    """
    ARQ task: send a single MessageDelivery.
    Uses exponential backoff via ARQ's retry mechanism.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.get(MessageDelivery, delivery_id)
        if result is None:
            return {"status": "not_found", "delivery_id": delivery_id}

        delivery: MessageDelivery = result

        if delivery.status in (MessageStatus.SENT, MessageStatus.BLOCKED):
            return {"status": "already_done", "delivery_id": delivery_id}

        # Load SMTP account
        account: SmtpAccount | None = await session.get(SmtpAccount, smtp_account_id)
        if account is None or not account.is_active or not account.is_verified:
            await mark_delivery_failed(session, delivery, "SMTP account not available.")
            return {"status": "smtp_unavailable", "delivery_id": delivery_id}

        # Load message body
        message = await session.get(delivery.__class__.__mapper__.relationships["message"].mapper.class_, delivery.message_id)
        if message is None:
            await mark_delivery_failed(session, delivery, "Message record not found.")
            return {"status": "message_not_found"}

        body = message.body
        if message.include_optout_footer:
            body += OPTOUT_FOOTER

        config = smtp_config_from_account(account)
        subject = ""  # Keep subject empty for SMS gateways
        success, error = await send_sms_via_smtp(config, delivery.gateway_address, subject, body)

        if success:
            await mark_delivery_sent(session, delivery)
            logger.info("delivery_sent", delivery_id=delivery_id, gateway=delivery.gateway_address)
            return {"status": "sent", "delivery_id": delivery_id}
        else:
            await mark_delivery_failed(session, delivery, error)
            logger.warning("delivery_failed", delivery_id=delivery_id, reason=error)
            return {"status": "failed", "delivery_id": delivery_id, "reason": error}


async def startup(ctx: dict) -> None:
    logger.info("arq_worker_startup")


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker_shutdown")


class WorkerSettings:
    functions = [send_delivery]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None  # set dynamically

    max_jobs = 10
    job_timeout = 60
    keep_result = 300

    # Retry with exponential backoff: 3 attempts, delays 5s, 30s, 120s
    max_tries = 3

    @classmethod
    def get_settings(cls):
        from arq.connections import RedisSettings
        settings = get_settings()
        return RedisSettings.from_dsn(settings.redis_url)
