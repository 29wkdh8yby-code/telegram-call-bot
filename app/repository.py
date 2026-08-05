"""Database repository: async CRUD helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt, encrypt
from app.models import (
    AuditAction,
    AuditLog,
    DailyUsage,
    Message,
    MessageDelivery,
    MessageStatus,
    OptOut,
    Recipient,
    SmtpAccount,
    User,
)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
    else:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def update_sender_name(session: AsyncSession, user: User, sender_name: str) -> None:
    user.sender_name = sender_name
    await session.commit()


async def suspend_user(session: AsyncSession, user: User, suspended: bool) -> None:
    user.is_suspended = suspended
    await session.commit()


async def set_user_daily_limit(session: AsyncSession, user: User, limit: int | None) -> None:
    user.daily_limit_override = limit
    await session.commit()


async def list_all_users(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# SMTP Accounts
# ---------------------------------------------------------------------------


async def create_smtp_account(
    session: AsyncSession,
    user: User,
    label: str,
    host: str,
    port: int,
    username: str,
    password_plaintext: str,
    encryption: str,
    sender_name: str | None = None,
) -> SmtpAccount:
    from app.models import SmtpEncryption

    account = SmtpAccount(
        user_id=user.id,
        label=label,
        host=host,
        port=port,
        username=username,
        encrypted_password=encrypt(password_plaintext),
        encryption=SmtpEncryption(encryption.upper()),
        sender_name=sender_name,
        is_verified=False,
        is_active=True,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def get_smtp_accounts(session: AsyncSession, user: User) -> Sequence[SmtpAccount]:
    result = await session.execute(
        select(SmtpAccount)
        .where(SmtpAccount.user_id == user.id, SmtpAccount.is_active == True)  # noqa: E712
        .order_by(SmtpAccount.created_at)
    )
    return result.scalars().all()


async def get_smtp_account(session: AsyncSession, account_id: int, user_id: int) -> SmtpAccount | None:
    result = await session.execute(
        select(SmtpAccount).where(SmtpAccount.id == account_id, SmtpAccount.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def verify_smtp_account(session: AsyncSession, account: SmtpAccount) -> None:
    account.is_verified = True
    await session.commit()


async def disable_smtp_account(session: AsyncSession, account: SmtpAccount) -> None:
    account.is_active = False
    await session.commit()


def get_plain_password(account: SmtpAccount) -> str:
    return decrypt(account.encrypted_password)


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------


async def add_recipient(
    session: AsyncSession,
    user: User,
    name: str,
    phone_e164: str,
    carrier: str,
    gateway_email: str,
    consent_confirmed: bool,
    consent_date: datetime | None = None,
    consent_notes: str | None = None,
) -> Recipient:
    recipient = Recipient(
        user_id=user.id,
        name=name,
        phone_e164=phone_e164,
        carrier=carrier,
        gateway_email=gateway_email,
        consent_confirmed=consent_confirmed,
        consent_date=consent_date or (datetime.now(UTC) if consent_confirmed else None),
        consent_notes=consent_notes,
        is_opted_out=False,
    )
    session.add(recipient)
    await session.commit()
    await session.refresh(recipient)
    return recipient


async def get_recipients(session: AsyncSession, user: User) -> Sequence[Recipient]:
    result = await session.execute(
        select(Recipient)
        .where(Recipient.user_id == user.id, Recipient.is_opted_out == False)  # noqa: E712
        .order_by(Recipient.name)
    )
    return result.scalars().all()


async def get_recipient(session: AsyncSession, recipient_id: int, user_id: int) -> Recipient | None:
    result = await session.execute(
        select(Recipient).where(Recipient.id == recipient_id, Recipient.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def opt_out_recipient(
    session: AsyncSession, recipient: Recipient, user: User, reason: str | None = None
) -> None:
    recipient.is_opted_out = True
    recipient.opted_out_at = datetime.now(UTC)
    opt_out = OptOut(
        recipient_id=recipient.id,
        recorded_by_user_id=user.id,
        reason=reason,
    )
    session.add(opt_out)
    await session.commit()


async def restore_consent(session: AsyncSession, recipient: Recipient) -> None:
    recipient.is_opted_out = False
    recipient.opted_out_at = None
    recipient.consent_confirmed = True
    recipient.consent_date = datetime.now(UTC)
    await session.commit()


# ---------------------------------------------------------------------------
# Messages & Deliveries
# ---------------------------------------------------------------------------


async def create_message(
    session: AsyncSession,
    user: User,
    smtp_account: SmtpAccount,
    body: str,
    include_optout_footer: bool = True,
) -> Message:
    message = Message(
        user_id=user.id,
        smtp_account_id=smtp_account.id,
        body=body,
        include_optout_footer=include_optout_footer,
        status=MessageStatus.QUEUED,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def create_delivery(
    session: AsyncSession,
    message: Message,
    user: User,
    recipient: Recipient,
) -> MessageDelivery:
    delivery = MessageDelivery(
        message_id=message.id,
        user_id=user.id,
        recipient_id=recipient.id,
        carrier=recipient.carrier,
        gateway_address=recipient.gateway_email,
        status=MessageStatus.QUEUED,
    )
    session.add(delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def mark_delivery_sent(session: AsyncSession, delivery: MessageDelivery) -> None:
    delivery.status = MessageStatus.SENT
    delivery.sent_at = datetime.now(UTC)
    await session.commit()


async def mark_delivery_failed(session: AsyncSession, delivery: MessageDelivery, reason: str) -> None:
    delivery.status = MessageStatus.FAILED
    delivery.failure_reason = reason
    await session.commit()


async def get_messages(session: AsyncSession, user: User, limit: int = 20) -> Sequence[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Daily Usage (DB-backed fallback)
# ---------------------------------------------------------------------------


async def get_or_create_daily_usage(session: AsyncSession, user: User, date_str: str) -> DailyUsage:
    result = await session.execute(
        select(DailyUsage).where(DailyUsage.user_id == user.id, DailyUsage.usage_date == date_str)
    )
    usage = result.scalar_one_or_none()
    if usage is None:
        usage = DailyUsage(user_id=user.id, usage_date=date_str, count=0)
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
    return usage


async def increment_daily_usage_db(session: AsyncSession, user: User, date_str: str) -> None:
    usage = await get_or_create_daily_usage(session, user, date_str)
    usage.count += 1
    await session.commit()


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


async def add_audit_log(
    session: AsyncSession,
    action: AuditAction,
    user: User | None = None,
    detail: str | None = None,
) -> None:
    log = AuditLog(
        user_id=user.id if user else None,
        action=action,
        detail=detail,
    )
    session.add(log)
    await session.commit()


async def get_audit_logs(session: AsyncSession, limit: int = 100) -> Sequence[AuditLog]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Admin stats
# ---------------------------------------------------------------------------


async def count_total_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def count_messages_today(session: AsyncSession, date_str: str) -> int:
    result = await session.execute(
        select(func.sum(DailyUsage.count)).where(DailyUsage.usage_date == date_str)
    )
    return int(result.scalar_one() or 0)


async def count_failed_today(session: AsyncSession) -> int:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    result = await session.execute(
        select(func.count()).select_from(MessageDelivery).where(
            MessageDelivery.status == MessageStatus.FAILED,
            func.date(MessageDelivery.created_at) == today,
        )
    )
    return result.scalar_one()
