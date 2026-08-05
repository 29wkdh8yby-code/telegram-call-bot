"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("is_suspended", sa.Boolean(), default=False, nullable=False),
        sa.Column("daily_limit_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    smtpencryption = sa.Enum("TLS", "SSL", name="smtpencryption")
    smtpencryption.create(op.get_bind())

    op.create_table(
        "smtp_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("encryption", smtpencryption, nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("is_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_smtp_accounts_user_id", "smtp_accounts", ["user_id"])

    op.create_table(
        "recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("carrier", sa.String(64), nullable=False),
        sa.Column("gateway_email", sa.String(255), nullable=False),
        sa.Column("consent_confirmed", sa.Boolean(), default=False, nullable=False),
        sa.Column("consent_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_notes", sa.Text(), nullable=True),
        sa.Column("is_opted_out", sa.Boolean(), default=False, nullable=False),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "phone_e164", name="uq_recipient_user_phone"),
    )
    op.create_index("ix_recipients_user_id", "recipients", ["user_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("consent_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "opt_outs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    messagestatus = sa.Enum("queued", "sending", "sent", "failed", "blocked", name="messagestatus")
    messagestatus.create(op.get_bind())

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("smtp_account_id", sa.Integer(), sa.ForeignKey("smtp_accounts.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("include_optout_footer", sa.Boolean(), default=True, nullable=False),
        sa.Column("status", messagestatus, nullable=False, default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    op.create_table(
        "message_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=False),
        sa.Column("carrier", sa.String(64), nullable=False),
        sa.Column("gateway_address", sa.String(255), nullable=False),
        sa.Column("status", messagestatus, nullable=False, default="queued"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_message_deliveries_message_id", "message_deliveries", ["message_id"])
    op.create_index("ix_message_deliveries_user_id", "message_deliveries", ["user_id"])
    op.create_index("ix_message_deliveries_recipient_id", "message_deliveries", ["recipient_id"])

    op.create_table(
        "daily_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_date", sa.String(10), nullable=False),
        sa.Column("count", sa.Integer(), default=0, nullable=False),
        sa.UniqueConstraint("user_id", "usage_date", name="uq_daily_usage_user_date"),
    )
    op.create_index("ix_daily_usage_user_id", "daily_usage", ["user_id"])
    op.create_index("ix_daily_usage_usage_date", "daily_usage", ["usage_date"])

    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_admins_telegram_id"),
    )

    auditaction = sa.Enum(
        "user_register", "smtp_add", "smtp_test", "recipient_add", "recipient_optout",
        "message_send", "message_fail", "admin_suspend", "admin_unsuspend",
        "admin_limit_change", "admin_smtp_disable",
        name="auditaction"
    )
    auditaction.create(op.get_bind())

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", auditaction, nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"])


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("audit_logs")
    op.execute("DROP TYPE IF EXISTS auditaction")
    op.drop_table("admins")
    op.drop_table("daily_usage")
    op.drop_table("message_deliveries")
    op.drop_table("messages")
    op.execute("DROP TYPE IF EXISTS messagestatus")
    op.drop_table("opt_outs")
    op.drop_table("consent_records")
    op.drop_table("recipients")
    op.drop_table("smtp_accounts")
    op.execute("DROP TYPE IF EXISTS smtpencryption")
    op.drop_table("users")
