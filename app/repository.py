from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.database import session_scope
from app.models import CallRecord, User

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}



def serialize_user(user: User) -> dict[str, Any]:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.display_name,
        "backend_user_id": user.backend_user_id,
        "selected_number": user.selected_number,
        "balance_credits": float(user.balance_credits),
    }



def serialize_call(call: CallRecord) -> dict[str, Any]:
    return {
        "call_id": call.external_call_id,
        "telegram_id": call.user.telegram_id if call.user else None,
        "source_number": call.source_number,
        "destination_number": call.destination_number,
        "status": call.status,
        "trunk_provider": call.trunk_provider,
        "duration_seconds": call.duration_seconds,
        "cost": float(call.cost),
        "error_message": call.error_message,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }



def upsert_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    *,
    display_name: str | None = None,
    backend_user_id: str | None = None,
    balance_credits: float | Decimal | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                display_name=display_name or first_name or username,
                backend_user_id=backend_user_id,
                balance_credits=Decimal(str(balance_credits if balance_credits is not None else 0.0)),
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.display_name = display_name or user.display_name or first_name or username
            if backend_user_id is not None:
                user.backend_user_id = backend_user_id
            if balance_credits is not None:
                user.balance_credits = Decimal(str(balance_credits))
        session.flush()
        session.refresh(user)
        return serialize_user(user)



def get_user(telegram_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        return serialize_user(user) if user else None



def update_selected_number(telegram_id: int, selected_number: str) -> dict[str, Any]:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            raise ValueError("User does not exist")
        user.selected_number = selected_number
        session.flush()
        session.refresh(user)
        return serialize_user(user)



def create_call_record(
    telegram_id: int,
    external_call_id: str,
    source_number: str,
    destination_number: str,
    status: str,
    trunk_provider: str,
) -> dict[str, Any]:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            raise ValueError("User does not exist")
        call = session.scalar(select(CallRecord).where(CallRecord.external_call_id == external_call_id))
        if call is None:
            call = CallRecord(
                user_id=user.id,
                external_call_id=external_call_id,
                source_number=source_number,
                destination_number=destination_number,
                status=status,
                trunk_provider=trunk_provider,
            )
            session.add(call)
        else:
            call.status = status
            call.source_number = source_number
            call.destination_number = destination_number
            call.trunk_provider = trunk_provider
        session.flush()
        session.refresh(call)
        return serialize_call(call)



def update_call_record(
    external_call_id: str,
    *,
    status: str,
    duration_seconds: int,
    cost: float | Decimal,
    ended_at: datetime | None,
    error_message: str | None = None,
    charge_user: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        call = session.scalar(select(CallRecord).where(CallRecord.external_call_id == external_call_id))
        if call is None:
            raise ValueError("Call does not exist")

        previous_status = call.status
        previous_cost = call.cost
        call.status = status
        call.duration_seconds = duration_seconds
        call.cost = Decimal(str(cost))
        call.ended_at = ended_at
        call.error_message = error_message

        if charge_user and previous_status not in TERMINAL_STATUSES and call.user:
            delta = call.cost - previous_cost
            if delta > 0:
                call.user.balance_credits = max(Decimal("0.00"), call.user.balance_credits - delta)

        session.flush()
        session.refresh(call)
        return serialize_call(call)



def get_recent_calls(telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return []
        calls = list(
            session.scalars(
                select(CallRecord)
                .where(CallRecord.user_id == user.id)
                .order_by(CallRecord.created_at.desc())
                .limit(limit)
            )
        )
        return [serialize_call(call) for call in calls]



def get_active_calls(telegram_id: int) -> list[dict[str, Any]]:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return []
        calls = list(
            session.scalars(
                select(CallRecord)
                .where(CallRecord.user_id == user.id, CallRecord.status.not_in(TERMINAL_STATUSES))
                .order_by(CallRecord.created_at.desc())
            )
        )
        return [serialize_call(call) for call in calls]
