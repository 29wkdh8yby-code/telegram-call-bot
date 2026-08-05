"""SQLAlchemy 2 ORM models for the SMTP-to-SMS Telegram bot."""
from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SmtpEncryption(str, enum.Enum):
    TLS = "TLS"
    SSL = "SSL"


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class AuditAction(str, enum.Enum):
    USER_REGISTER = "user_register"
    SMTP_ADD = "smtp_add"
    SMTP_TEST = "smtp_test"
    RECIPIENT_ADD = "recipient_add"
    RECIPIENT_OPTOUT = "recipient_optout"
    MESSAGE_SEND = "message_send"
    MESSAGE_FAIL = "message_fail"
    ADMIN_SUSPEND = "admin_suspend"
    ADMIN_UNSUSPEND = "admin_unsuspend"
    ADMIN_LIMIT_CHANGE = "admin_limit_change"
    ADMIN_SMTP_DISABLE = "admin_smtp_disable"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow
    )

    smtp_accounts: Mapped[list["SmtpAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    recipients: Mapped[list["Recipient"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_usages: Mapped[list["DailyUsage"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# SMTP Accounts
# ---------------------------------------------------------------------------


class SmtpAccount(Base):
    __tablename__ = "smtp_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="Default")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted password stored as base64 Fernet token
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    encryption: Mapped[SmtpEncryption] = mapped_column(
        Enum(SmtpEncryption, name="smtpencryption"), nullable=False, default=SmtpEncryption.TLS
    )
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="smtp_accounts")
    messages: Mapped[list["Message"]] = relationship(back_populates="smtp_account")


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Normalized E.164 phone number
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    # Derived gateway email, e.g. 2025551234@txt.att.net
    gateway_email: Mapped[str] = mapped_column(String(255), nullable=False)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="recipients")
    deliveries: Mapped[list["MessageDelivery"]] = relationship(back_populates="recipient")
    opt_outs: Mapped[list["OptOut"]] = relationship(back_populates="recipient")

    __table_args__ = (UniqueConstraint("user_id", "phone_e164", name="uq_recipient_user_phone"),)


# ---------------------------------------------------------------------------
# Consent Records
# ---------------------------------------------------------------------------


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("recipients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    consent_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


# ---------------------------------------------------------------------------
# Opt-Outs
# ---------------------------------------------------------------------------


class OptOut(Base):
    __tablename__ = "opt_outs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("recipients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    recipient: Mapped["Recipient"] = relationship(back_populates="opt_outs")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    smtp_account_id: Mapped[int | None] = mapped_column(ForeignKey("smtp_accounts.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    include_optout_footer: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="messagestatus"), nullable=False, default=MessageStatus.QUEUED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="messages")
    smtp_account: Mapped["SmtpAccount | None"] = relationship(back_populates="messages")
    deliveries: Mapped[list["MessageDelivery"]] = relationship(back_populates="message", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Message Deliveries
# ---------------------------------------------------------------------------


class MessageDelivery(Base):
    __tablename__ = "message_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id"), index=True, nullable=False)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    gateway_address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="messagestatus"), nullable=False, default=MessageStatus.QUEUED
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message: Mapped["Message"] = relationship(back_populates="deliveries")
    recipient: Mapped["Recipient"] = relationship(back_populates="deliveries")


# ---------------------------------------------------------------------------
# Daily Usage
# ---------------------------------------------------------------------------


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # Date string YYYY-MM-DD in the configured timezone
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="daily_usages")

    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_daily_usage_user_date"),)


# ---------------------------------------------------------------------------
# Admins
# ---------------------------------------------------------------------------


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="auditaction"), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="audit_logs")


# ---------------------------------------------------------------------------
# System Settings
# ---------------------------------------------------------------------------


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow
    )
