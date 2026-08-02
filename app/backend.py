from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from flask import Flask, jsonify, request

from app.config import Settings, load_settings
from app.database import init_database
from app.repository import (
    create_call_record,
    get_recent_calls,
    get_user,
    serialize_call,
    update_call_record,
    update_selected_number,
    upsert_user,
)
from app.database import session_scope
from app.models import CallRecord
from sqlalchemy import select

RATE_PER_MINUTE = Decimal("0.05")
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}



def _calculate_cost(duration_seconds: int) -> Decimal:
    minutes = Decimal(duration_seconds) / Decimal(60)
    return (minutes * RATE_PER_MINUTE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _progress_call(call: CallRecord) -> tuple[str, int, datetime | None]:
    if call.status in TERMINAL_STATUSES:
        return call.status, call.duration_seconds, call.ended_at

    elapsed = max(0, int((datetime.now(UTC) - _as_utc(call.started_at)).total_seconds()))
    if elapsed < 5:
        return "ringing", 0, None
    if elapsed < 20:
        return "in_progress", elapsed - 5, None
    return "completed", 15, call.started_at + timedelta(seconds=20)



def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    init_database(settings.database_url)

    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.post("/api/auth/telegram")
    def auth_telegram():
        payload = request.get_json(silent=True) or {}
        telegram_id = payload.get("telegram_id")
        if not telegram_id:
            return jsonify({"error": "telegram_id is required"}), 400

        user = upsert_user(
            telegram_id=int(telegram_id),
            username=payload.get("username"),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            display_name=payload.get("display_name") or payload.get("first_name") or payload.get("username"),
            backend_user_id=payload.get("backend_user_id") or f"user-{telegram_id}",
            balance_credits=payload.get("balance_credits", settings.default_user_credits),
        )
        return jsonify({"user": user}), 200

    @app.get("/api/users/<int:telegram_id>")
    def get_user_profile(telegram_id: int):
        user = get_user(telegram_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": user}), 200

    @app.get("/api/numbers")
    def available_numbers():
        return jsonify({"numbers": list(settings.available_numbers), "trunk_provider": settings.trunk_provider_name}), 200

    @app.post("/api/users/<int:telegram_id>/selected-number")
    def save_selected_number(telegram_id: int):
        payload = request.get_json(silent=True) or {}
        selected_number = payload.get("selected_number")
        if selected_number not in settings.available_numbers:
            return jsonify({"error": "Selected number is not available"}), 400
        try:
            user = update_selected_number(telegram_id, selected_number)
        except ValueError:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": user}), 200

    @app.post("/api/calls")
    def place_call():
        payload = request.get_json(silent=True) or {}
        telegram_id = payload.get("telegram_id")
        source_number = payload.get("source_number")
        destination_number = payload.get("destination_number")
        user = get_user(int(telegram_id)) if telegram_id else None

        if not telegram_id or not source_number or not destination_number:
            return jsonify({"error": "telegram_id, source_number, and destination_number are required"}), 400
        if not user:
            return jsonify({"error": "User not found"}), 404
        if source_number not in settings.available_numbers:
            return jsonify({"error": "Source number is not provisioned"}), 400
        if user["balance_credits"] <= 0:
            return jsonify({"error": "Insufficient credits"}), 402

        call_id = f"call-{uuid4().hex[:12]}"
        call = create_call_record(
            telegram_id=int(telegram_id),
            external_call_id=call_id,
            source_number=source_number,
            destination_number=destination_number,
            status="queued",
            trunk_provider=settings.trunk_provider_name,
        )
        update_selected_number(int(telegram_id), source_number)
        return jsonify(call), 201

    @app.get("/api/calls/<string:call_id>")
    def get_call_status(call_id: str):
        with session_scope() as session:
            call = session.scalar(select(CallRecord).where(CallRecord.external_call_id == call_id))
            if call is None:
                return jsonify({"error": "Call not found"}), 404
            status, duration, ended_at = _progress_call(call)
            updated = update_call_record(
                call_id,
                status=status,
                duration_seconds=duration,
                cost=float(_calculate_cost(duration)),
                ended_at=ended_at,
                charge_user=status in TERMINAL_STATUSES,
            )
            return jsonify(updated), 200

    @app.post("/api/calls/<string:call_id>/end")
    def end_call(call_id: str):
        with session_scope() as session:
            call = session.scalar(select(CallRecord).where(CallRecord.external_call_id == call_id))
            if call is None:
                return jsonify({"error": "Call not found"}), 404
            if call.status in TERMINAL_STATUSES:
                return jsonify(serialize_call(call)), 200
            elapsed = max(0, int((datetime.now(UTC) - _as_utc(call.started_at)).total_seconds()))
            duration = max(0, elapsed - 5)
            final_status = "cancelled" if duration == 0 else "completed"
            updated = update_call_record(
                call_id,
                status=final_status,
                duration_seconds=duration,
                cost=float(_calculate_cost(duration)),
                ended_at=datetime.now(UTC),
                charge_user=final_status == "completed",
            )
            return jsonify(updated), 200

    @app.get("/api/users/<int:telegram_id>/calls")
    def call_history(telegram_id: int):
        return jsonify({"calls": get_recent_calls(telegram_id)}), 200

    return app


if __name__ == "__main__":
    settings = load_settings()
    create_app(settings).run(host=settings.backend_host, port=settings.backend_port, debug=False)
