"""Message sending flow handlers."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import get_session_factory
from app.handlers.keyboards import back_keyboard, cancel_keyboard
from app.models import AuditAction, MessageStatus
from app.repository import (
    add_audit_log,
    create_delivery,
    create_message,
    get_recipients,
    get_smtp_accounts,
    get_user_by_telegram_id,
)
from app.services.rate_limiter import check_and_increment, get_daily_usage

logger = structlog.get_logger(__name__)
router = Router(name="messaging")

OPTOUT_FOOTER = "\n\nReply STOP to opt out or contact sender to unsubscribe."


class SendMessageStates(StatesGroup):
    select_smtp = State()
    select_recipients = State()
    compose = State()
    preview = State()


@router.callback_query(F.data == "menu:send")
async def cb_send_start(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    if db_user and db_user.is_suspended:
        await query.answer("Your account is suspended. Contact admin.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        smtp_accounts = await get_smtp_accounts(session, user) if user else []

    if not smtp_accounts:
        await query.message.edit_text(
            "⚠️ You need to set up an SMTP account first.\n"
            "Go to ⚙️ Account Settings → Add SMTP Account.",
            reply_markup=back_keyboard(),
        )
        await query.answer()
        return

    verified = [a for a in smtp_accounts if a.is_verified]
    if not verified:
        await query.message.edit_text(
            "⚠️ No verified SMTP accounts. Please set up and test an SMTP account in Settings.",
            reply_markup=back_keyboard("menu:settings"),
        )
        await query.answer()
        return

    if len(verified) == 1:
        await state.update_data(smtp_account_id=verified[0].id)
        await _show_recipient_selection(query, state, db_user)
    else:
        buttons = [
            [InlineKeyboardButton(text=f"📧 {a.label} ({a.username})", callback_data=f"send_smtp:{a.id}")]
            for a in verified
        ]
        buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")])
        await state.set_state(SendMessageStates.select_smtp)
        await query.message.edit_text(
            "Select SMTP account to send from:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await query.answer()


@router.callback_query(F.data.startswith("send_smtp:"))
async def cb_select_smtp(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    smtp_id = int(query.data.split(":")[-1])
    await state.update_data(smtp_account_id=smtp_id)
    await _show_recipient_selection(query, state, db_user)
    await query.answer()


async def _show_recipient_selection(query: CallbackQuery, state: FSMContext, db_user) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        recipients = await get_recipients(session, user) if user else []

    consented = [r for r in recipients if r.consent_confirmed and not r.is_opted_out]
    if not consented:
        await query.message.edit_text(
            "⚠️ No consented recipients. Add recipients with consent first.",
            reply_markup=back_keyboard(),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"👤 {r.name} ({r.phone_e164})",
            callback_data=f"toggle_recipient:{r.id}"
        )]
        for r in consented
    ]
    buttons.append([
        InlineKeyboardButton(text="✅ Done — Compose Message", callback_data="recipients_done"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
    ])

    await state.update_data(selected_recipients=[], all_recipients=[r.id for r in consented])
    await state.set_state(SendMessageStates.select_recipients)
    await query.message.edit_text(
        "Select one or more recipients (tap to toggle ✅):\n\nSelected: none",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("toggle_recipient:"))
async def cb_toggle_recipient(query: CallbackQuery, state: FSMContext) -> None:
    rid = int(query.data.split(":")[-1])
    data = await state.get_data()
    selected: list[int] = list(data.get("selected_recipients", []))

    if rid in selected:
        selected.remove(rid)
    else:
        selected.append(rid)

    await state.update_data(selected_recipients=selected)

    # Rebuild keyboard showing selected state
    all_ids: list[int] = data.get("all_recipients", [])
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select as sa_select
        from app.models import Recipient
        result = await session.execute(sa_select(Recipient).where(Recipient.id.in_(all_ids)))
        recipients = {r.id: r for r in result.scalars().all()}

    buttons = []
    for rid_btn in all_ids:
        r = recipients.get(rid_btn)
        if not r:
            continue
        mark = "✅ " if rid_btn in selected else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{r.name} ({r.phone_e164})",
            callback_data=f"toggle_recipient:{rid_btn}"
        )])

    buttons.append([
        InlineKeyboardButton(text="✅ Done — Compose Message", callback_data="recipients_done"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
    ])

    selected_count = len(selected)
    await query.message.edit_text(
        f"Select recipients (tap to toggle ✅):\n\nSelected: {selected_count}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(F.data == "recipients_done")
async def cb_recipients_done(query: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("selected_recipients", [])
    if not selected:
        await query.answer("Please select at least one recipient.", show_alert=True)
        return
    await state.set_state(SendMessageStates.compose)
    await query.message.edit_text(
        f"📝 Compose your message ({len(selected)} recipient(s) selected):\n\n"
        "Type your message below. Keep it short — SMS messages are limited.\n"
        "An opt-out footer will be automatically appended.",
        reply_markup=cancel_keyboard(),
    )
    await query.answer()


@router.message(SendMessageStates.compose)
async def compose_message(message: Message, state: FSMContext) -> None:
    body = (message.text or "").strip()
    if not body:
        await message.answer("Message cannot be empty.")
        return
    if len(body) > 1000:
        await message.answer(f"Message too long ({len(body)} chars). Please keep it under 1000 characters.")
        return

    await state.update_data(message_body=body)
    data = await state.get_data()
    selected_count = len(data.get("selected_recipients", []))
    full_message = body + OPTOUT_FOOTER

    preview_text = (
        f"📋 <b>Preview</b>\n\n"
        f"Sending to <b>{selected_count}</b> opted-in recipient(s).\n\n"
        f"<b>Message:</b>\n{full_message}\n\n"
        f"Confirm to send?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Confirm Send", callback_data="send_confirm"),
            InlineKeyboardButton(text="✏️ Edit Message", callback_data="send_edit"),
        ],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")],
    ])
    await state.set_state(SendMessageStates.preview)
    await message.answer(preview_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "send_edit")
async def cb_send_edit(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SendMessageStates.compose)
    data = await state.get_data()
    selected_count = len(data.get("selected_recipients", []))
    await query.message.edit_text(
        f"✏️ Re-enter your message ({selected_count} recipient(s)):",
        reply_markup=cancel_keyboard(),
    )
    await query.answer()


@router.callback_query(F.data == "send_confirm")
async def cb_send_confirm(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    data = await state.get_data()
    selected_ids: list[int] = data.get("selected_recipients", [])
    smtp_account_id: int = data.get("smtp_account_id")
    body: str = data.get("message_body", "")
    await state.clear()

    # Rate limit check
    allowed, reason = await check_and_increment(db_user.telegram_id)
    if not allowed:
        await query.message.edit_text(f"⏱ {reason}", reply_markup=back_keyboard())
        await query.answer()
        return

    await query.message.edit_text("🔄 Queuing messages…")

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.message.edit_text("User not found.")
            return

        from app.repository import get_smtp_account
        smtp_account = await get_smtp_account(session, smtp_account_id, user.id)
        if not smtp_account:
            await query.message.edit_text("SMTP account not found.")
            return

        message_record = await create_message(session, user, smtp_account, body)

        # Load recipients
        from sqlalchemy import select as sa_select
        from app.models import Recipient
        result = await session.execute(
            sa_select(Recipient).where(
                Recipient.id.in_(selected_ids),
                Recipient.user_id == user.id,
                Recipient.consent_confirmed == True,  # noqa: E712
                Recipient.is_opted_out == False,  # noqa: E712
            )
        )
        recipients = result.scalars().all()

        queued = 0
        blocked = 0
        for r in recipients:
            delivery = await create_delivery(session, message_record, user, r)
            # Enqueue in ARQ
            try:
                import arq
                from app.config import get_settings
                from arq.connections import RedisSettings
                settings = get_settings()
                redis_settings = RedisSettings.from_dsn(settings.redis_url)
                arq_redis = await arq.create_pool(redis_settings)
                await arq_redis.enqueue_job(
                    "send_delivery",
                    delivery.id,
                    smtp_account_id,
                )
                await arq_redis.aclose()
                queued += 1
            except Exception as exc:
                logger.error("enqueue_error", exc=str(exc))
                from app.repository import mark_delivery_failed
                await mark_delivery_failed(session, delivery, f"Enqueue failed: {exc}")
                blocked += 1

        await add_audit_log(
            session, AuditAction.MESSAGE_SEND, user,
            f"Queued {queued} message(s) to {len(recipients)} recipients"
        )

    used, limit = await get_daily_usage(db_user.telegram_id)
    status_text = (
        f"✅ <b>{queued}</b> message(s) queued for sending.\n"
    )
    if blocked:
        status_text += f"⚠️ {blocked} could not be queued.\n"
    status_text += f"\n📊 Daily Usage: {used} / {limit}\nRemaining Today: {limit - used}"

    await query.message.edit_text(status_text, parse_mode="HTML", reply_markup=back_keyboard())
    await query.answer()
