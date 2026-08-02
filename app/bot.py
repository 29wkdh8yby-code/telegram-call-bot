from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.api_client import BackendApiClient, BackendApiError
from app.config import Settings
from app.database import init_database
from app.repository import (
    create_call_record,
    get_active_calls,
    get_recent_calls,
    get_user,
    update_call_record,
    update_selected_number,
    upsert_user,
)

LOGGER = logging.getLogger(__name__)
DESTINATION = 1
PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _parse_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    return datetime.fromisoformat(raw_value)


class CallServiceBot:
    def __init__(self, settings: Settings):
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot.")
        self.settings = settings
        self.api_client = BackendApiClient(settings.backend_api_base_url, timeout=settings.request_timeout)
        self.application: Application | None = None
        init_database(settings.database_url)

    def build_application(self) -> Application:
        application = Application.builder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("profile", self.profile))
        application.add_handler(CommandHandler("balance", self.balance))
        application.add_handler(CommandHandler("numbers", self.numbers))
        application.add_handler(CallbackQueryHandler(self.select_number, pattern=r"^select_number:"))
        application.add_handler(CommandHandler("history", self.history))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("end", self.end_call))
        application.add_handler(
            ConversationHandler(
                entry_points=[CommandHandler("call", self.begin_call)],
                states={DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.place_call)]},
                fallbacks=[CommandHandler("cancel", self.cancel)],
            )
        )
        self.application = application
        return application

    async def _backend_call(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    async def _sync_user(self, telegram_user) -> dict[str, Any]:
        local_user = upsert_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        payload = {
            "telegram_id": telegram_user.id,
            "username": telegram_user.username,
            "first_name": telegram_user.first_name,
            "last_name": telegram_user.last_name,
            "display_name": local_user.get("display_name") or telegram_user.first_name or telegram_user.username,
            "selected_number": local_user.get("selected_number"),
        }
        response = await self._backend_call(self.api_client.authenticate_user, payload)
        backend_user = response["user"]
        return upsert_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            display_name=backend_user.get("display_name"),
            backend_user_id=backend_user.get("backend_user_id"),
            balance_credits=backend_user.get("balance_credits"),
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        try:
            user = await self._sync_user(update.effective_user)
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to register you right now: {exc}")
            return

        message = (
            f"Welcome {user.get('display_name') or 'there'}!\n\n"
            "Use /numbers to choose your caller ID, /call to place a call, /status for live updates, "
            "/history for recent calls, and /balance to check credits."
        )
        await update.effective_message.reply_text(message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        await update.effective_message.reply_text(
            "/start - Register or login\n"
            "/profile - View your profile\n"
            "/balance - Check credits\n"
            "/numbers - Pick an available number\n"
            "/call - Start a new call\n"
            "/status - View active calls\n"
            "/history - View recent calls\n"
            "/end - Disconnect your latest active call\n"
            "/cancel - Cancel call entry"
        )

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        try:
            user = await self._sync_user(update.effective_user)
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to load profile: {exc}")
            return

        username = f"@{user['username']}" if user.get("username") else "-"
        await update.effective_message.reply_text(
            f"Profile\nName: {user.get('display_name') or '-'}\nUsername: {username}"
        )
        selected_number = user.get("selected_number") or "Not selected"
        await update.effective_message.reply_text(
            f"Selected number: {selected_number}\nBalance: {user.get('balance_credits', 0):.2f} credits"
        )

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        try:
            response = await self._backend_call(self.api_client.get_user_profile, update.effective_user.id)
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to fetch balance: {exc}")
            return
        backend_user = response["user"]
        upsert_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
            display_name=backend_user.get("display_name"),
            backend_user_id=backend_user.get("backend_user_id"),
            balance_credits=backend_user.get("balance_credits"),
        )
        await update.effective_message.reply_text(
            f"Your current balance is {backend_user.get('balance_credits', 0):.2f} credits."
        )

    async def numbers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        try:
            response = await self._backend_call(self.api_client.get_available_numbers)
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to load numbers: {exc}")
            return

        keyboard = [
            [InlineKeyboardButton(number, callback_data=f"select_number:{number}")]
            for number in response.get("numbers", [])
        ]
        await update.effective_message.reply_text(
            f"Available numbers from {response.get('trunk_provider', 'the backend')}:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def select_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        query = update.callback_query
        await query.answer()
        selected_number = query.data.split(":", 1)[1]
        try:
            await self._sync_user(update.effective_user)
            backend_response = await self._backend_call(
                self.api_client.save_selected_number,
                update.effective_user.id,
                selected_number,
            )
        except BackendApiError as exc:
            await query.edit_message_text(f"Unable to save your caller ID: {exc}")
            return
        update_selected_number(update.effective_user.id, backend_response["user"]["selected_number"])
        await query.edit_message_text(f"Selected caller ID: {selected_number}")

    async def begin_call(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = get_user(update.effective_user.id)
        if not user or not user.get("selected_number"):
            await update.effective_message.reply_text("Choose a caller ID first with /numbers.")
            return ConversationHandler.END
        context.user_data["source_number"] = user["selected_number"]
        await update.effective_message.reply_text("Send the destination number in E.164 format, for example +12025550199")
        return DESTINATION

    async def place_call(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        destination_number = (update.effective_message.text or "").strip()
        if not PHONE_PATTERN.match(destination_number):
            await update.effective_message.reply_text("Please send a valid destination number such as +12025550199")
            return DESTINATION

        source_number = context.user_data.get("source_number")
        try:
            response = await self._backend_call(
                self.api_client.place_call,
                update.effective_user.id,
                source_number,
                destination_number,
            )
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to place the call: {exc}")
            return ConversationHandler.END

        create_call_record(
            telegram_id=update.effective_user.id,
            external_call_id=response["call_id"],
            source_number=response["source_number"],
            destination_number=response["destination_number"],
            status=response["status"],
            trunk_provider=response["trunk_provider"],
        )

        await update.effective_message.reply_text(
            f"Call queued.\nCall ID: {response['call_id']}\nFrom: {response['source_number']}\nTo: {response['destination_number']}"
        )
        if self.application is not None:
            self.application.create_task(self.monitor_call(update.effective_chat.id, response["call_id"]))
        return ConversationHandler.END

    async def monitor_call(self, chat_id: int, call_id: str) -> None:
        last_status = None
        while True:
            try:
                response = await self._backend_call(self.api_client.get_call_status, call_id)
            except BackendApiError as exc:
                LOGGER.warning("Failed to poll call %s: %s", call_id, exc)
                return

            update_call_record(
                call_id,
                status=response["status"],
                duration_seconds=response.get("duration_seconds", 0),
                cost=response.get("cost", 0.0),
                ended_at=_parse_timestamp(response.get("ended_at")),
                error_message=response.get("error_message"),
            )
            if response["status"] != last_status and self.application is not None:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Call {call_id} status: {response['status']}"
                        f"\nDuration: {response.get('duration_seconds', 0)}s"
                        f"\nCost: {response.get('cost', 0.0):.2f}"
                    ),
                )
                last_status = response["status"]
            if response["status"] in TERMINAL_STATUSES:
                return
            await asyncio.sleep(self.settings.status_poll_interval)

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        try:
            response = await self._backend_call(self.api_client.get_call_history, update.effective_user.id)
            calls = response.get("calls", [])[:5]
            for call in calls:
                create_call_record(
                    telegram_id=update.effective_user.id,
                    external_call_id=call["call_id"],
                    source_number=call["source_number"],
                    destination_number=call["destination_number"],
                    status=call["status"],
                    trunk_provider=call["trunk_provider"],
                )
                update_call_record(
                    call["call_id"],
                    status=call["status"],
                    duration_seconds=call.get("duration_seconds", 0),
                    cost=call.get("cost", 0.0),
                    ended_at=_parse_timestamp(call.get("ended_at")),
                    error_message=call.get("error_message"),
                )
        except (BackendApiError, ValueError):
            calls = get_recent_calls(update.effective_user.id, limit=5)
        if not calls:
            await update.effective_message.reply_text("No calls yet.")
            return
        lines = ["Recent calls:"]
        for call in calls:
            lines.append(
                f"{call['call_id']}: {call['source_number']} -> {call['destination_number']} | "
                f"{call['status']} | {call['duration_seconds']}s | {call['cost']:.2f} credits"
            )
        await update.effective_message.reply_text("\n".join(lines))

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        calls = get_active_calls(update.effective_user.id)
        if not calls:
            await update.effective_message.reply_text("You have no active calls.")
            return
        lines = ["Active calls:"]
        for call in calls:
            try:
                latest = await self._backend_call(self.api_client.get_call_status, call["call_id"])
                update_call_record(
                    call["call_id"],
                    status=latest["status"],
                    duration_seconds=latest.get("duration_seconds", 0),
                    cost=latest.get("cost", 0.0),
                    ended_at=_parse_timestamp(latest.get("ended_at")),
                    error_message=latest.get("error_message"),
                )
                call = latest
            except BackendApiError as exc:
                LOGGER.warning("Failed to refresh call status for %s: %s", call["call_id"], exc)
            lines.append(
                f"{call['call_id']}: {call['status']} | {call.get('duration_seconds', 0)}s | {call.get('cost', 0.0):.2f} credits"
            )
        await update.effective_message.reply_text("\n".join(lines))

    async def end_call(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        active_calls = get_active_calls(update.effective_user.id)
        if not active_calls:
            await update.effective_message.reply_text("You have no active calls to end.")
            return
        call_id = active_calls[0]["call_id"]
        try:
            response = await self._backend_call(self.api_client.end_call, call_id)
        except BackendApiError as exc:
            await update.effective_message.reply_text(f"Unable to end the call: {exc}")
            return
        update_call_record(
            call_id,
            status=response["status"],
            duration_seconds=response.get("duration_seconds", 0),
            cost=response.get("cost", 0.0),
            ended_at=_parse_timestamp(response.get("ended_at")),
            error_message=response.get("error_message"),
        )
        await update.effective_message.reply_text(
            f"Call {call_id} ended with status {response['status']}. Cost: {response.get('cost', 0.0):.2f}"
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        del context
        await update.effective_message.reply_text("Call request cancelled.")
        return ConversationHandler.END

    def run(self) -> None:
        self.build_application().run_polling(drop_pending_updates=True)
