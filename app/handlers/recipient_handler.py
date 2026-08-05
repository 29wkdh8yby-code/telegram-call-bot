"""Recipient management handlers."""
from __future__ import annotations

import re

import phonenumbers
import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.carriers import build_gateway_email, list_carriers
from app.database import get_session_factory
from app.handlers.keyboards import back_keyboard, cancel_keyboard
from app.models import AuditAction
from app.repository import (
    add_audit_log,
    add_recipient,
    get_recipient,
    get_recipients,
    opt_out_recipient,
    restore_consent,
)

logger = structlog.get_logger(__name__)
router = Router(name="recipients")


class AddRecipientStates(StatesGroup):
    name = State()
    phone = State()
    carrier = State()
    consent = State()
    consent_notes = State()
    confirm = State()


def _normalize_phone(text: str) -> str | None:
    """Parse and normalize to E.164. Returns None on failure."""
    text = text.strip()
    try:
        parsed = phonenumbers.parse(text, "US")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def _phone_digits(e164: str) -> str:
    """Strip +1 country code, return 10-digit string."""
    digits = re.sub(r"[^\d]", "", e164)
    if digits.startswith("1") and len(digits) == 11:
        return digits[1:]
    return digits


def _carrier_keyboard() -> InlineKeyboardMarkup:
    carriers = list_carriers()
    buttons = []
    row = []
    for carrier in carriers:
        row.append(InlineKeyboardButton(text=carrier.display_name, callback_data=f"carrier:{carrier.key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "menu:add_recipient")
async def cb_add_recipient_start(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    if db_user and db_user.is_suspended:
        await query.answer("Your account is suspended.", show_alert=True)
        return
    await state.set_state(AddRecipientStates.name)
    await query.message.edit_text(
        "➕ <b>Add New Recipient</b>\n\nEnter the recipient's name:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await query.answer()


@router.message(AddRecipientStates.name)
async def add_recipient_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Please enter a name.")
        return
    await state.update_data(name=name)
    await state.set_state(AddRecipientStates.phone)
    await message.answer(
        "Enter the recipient's US phone number:\n(e.g. <code>2025551234</code> or <code>+12025551234</code>)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@router.message(AddRecipientStates.phone)
async def add_recipient_phone(message: Message, state: FSMContext) -> None:
    phone = _normalize_phone(message.text or "")
    if not phone:
        await message.answer("Invalid phone number. Please enter a US number, e.g. 2025551234.")
        return
    await state.update_data(phone=phone)
    await state.set_state(AddRecipientStates.carrier)
    await message.answer("Select the recipient's mobile carrier:", reply_markup=_carrier_keyboard())


@router.callback_query(F.data.startswith("carrier:"))
async def add_recipient_carrier(query: CallbackQuery, state: FSMContext) -> None:
    carrier_key = query.data.split(":", 1)[1]
    await state.update_data(carrier=carrier_key)
    await state.set_state(AddRecipientStates.consent)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, they have consented", callback_data="consent:yes"),
            InlineKeyboardButton(text="❌ No / Not sure", callback_data="consent:no"),
        ]
    ])
    await query.message.edit_text(
        "⚠️ <b>Consent Confirmation Required</b>\n\n"
        "Has this recipient explicitly agreed to receive SMS notifications from you?\n\n"
        "You must only send messages to people who have opted in.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@router.callback_query(F.data == "consent:no")
async def consent_no(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.message.edit_text(
        "❌ Recipient not added.\n\nYou can only add recipients who have explicitly consented to receive messages.",
        reply_markup=back_keyboard(),
    )
    await query.answer()


@router.callback_query(F.data == "consent:yes")
async def consent_yes(query: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(consent_confirmed=True)
    await state.set_state(AddRecipientStates.consent_notes)
    await query.message.edit_text(
        "Optionally, add a consent note (e.g. <i>Signed up via website form on 2024-01-15</i>).\n"
        "Or tap <b>Skip</b> to continue.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Skip", callback_data="consent_notes:skip")]
        ]),
    )
    await query.answer()


@router.callback_query(F.data == "consent_notes:skip")
async def consent_notes_skip(query: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(consent_notes=None)
    await _show_recipient_confirm(query, state)
    await query.answer()


@router.message(AddRecipientStates.consent_notes)
async def add_recipient_consent_notes(message: Message, state: FSMContext) -> None:
    notes = (message.text or "").strip() or None
    await state.update_data(consent_notes=notes)
    await _show_recipient_confirm_msg(message, state)


async def _show_recipient_confirm(query: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    from app.carriers import get_carrier
    carrier = get_carrier(data["carrier"])
    carrier_name = carrier.display_name if carrier else data["carrier"]
    digits = _phone_digits(data["phone"])
    gateway = build_gateway_email(digits, data["carrier"]) or "unknown"

    text = (
        f"📋 <b>Review Recipient</b>\n\n"
        f"Name: {data['name']}\n"
        f"Phone: {data['phone']}\n"
        f"Carrier: {carrier_name}\n"
        f"Gateway: <code>{gateway}</code>\n"
        f"Consented: ✅\n"
        f"Notes: {data.get('consent_notes') or '-'}\n\n"
        "Add this recipient?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Add", callback_data="recipient_confirm:add"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
        ]
    ])
    await state.set_state(AddRecipientStates.confirm)
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _show_recipient_confirm_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    from app.carriers import get_carrier
    carrier = get_carrier(data["carrier"])
    carrier_name = carrier.display_name if carrier else data["carrier"]
    digits = _phone_digits(data["phone"])
    gateway = build_gateway_email(digits, data["carrier"]) or "unknown"

    text = (
        f"📋 <b>Review Recipient</b>\n\n"
        f"Name: {data['name']}\n"
        f"Phone: {data['phone']}\n"
        f"Carrier: {carrier_name}\n"
        f"Gateway: <code>{gateway}</code>\n"
        f"Consented: ✅\n"
        f"Notes: {data.get('consent_notes') or '-'}\n\n"
        "Add this recipient?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Add", callback_data="recipient_confirm:add"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
        ]
    ])
    await state.set_state(AddRecipientStates.confirm)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "recipient_confirm:add")
async def recipient_confirm_add(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    data = await state.get_data()
    await state.clear()

    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    digits = _phone_digits(data["phone"])
    gateway = build_gateway_email(digits, data["carrier"])

    if not gateway:
        await query.message.edit_text("❌ Could not determine gateway for carrier.")
        return

    factory = get_session_factory()
    async with factory() as session:
        # Refresh user from this session
        from app.repository import get_user_by_telegram_id
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.answer("User not found.", show_alert=True)
            return

        try:
            recipient = await add_recipient(
                session,
                user=user,
                name=data["name"],
                phone_e164=data["phone"],
                carrier=data["carrier"],
                gateway_email=gateway,
                consent_confirmed=data.get("consent_confirmed", False),
                consent_notes=data.get("consent_notes"),
            )
            await add_audit_log(
                session, AuditAction.RECIPIENT_ADD, user,
                f"Added recipient {data['name']} ({data['phone']})"
            )
            await query.message.edit_text(
                f"✅ Recipient <b>{data['name']}</b> added successfully!\n"
                f"Gateway: <code>{gateway}</code>",
                parse_mode="HTML",
                reply_markup=back_keyboard(),
            )
        except Exception as exc:
            if "uq_recipient_user_phone" in str(exc):
                await query.message.edit_text(
                    "⚠️ This phone number is already in your recipients list.",
                    reply_markup=back_keyboard(),
                )
            else:
                logger.error("add_recipient_error", exc=str(exc))
                await query.message.edit_text("❌ Failed to add recipient. Try again.")

    await query.answer()


@router.callback_query(F.data == "menu:recipients")
async def cb_list_recipients(query: CallbackQuery, db_user=None) -> None:
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        from app.repository import get_user_by_telegram_id
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        recipients = await get_recipients(session, user) if user else []

    if not recipients:
        await query.message.edit_text(
            "You have no active recipients.\nUse ➕ Add Recipient to get started.",
            reply_markup=back_keyboard(),
        )
        await query.answer()
        return

    buttons = [
        [InlineKeyboardButton(text=f"👤 {r.name} ({r.phone_e164})", callback_data=f"recipient:view:{r.id}")]
        for r in recipients
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:main")])
    await query.message.edit_text(
        f"👥 <b>My Recipients</b> ({len(recipients)} active):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(F.data.startswith("recipient:view:"))
async def cb_view_recipient(query: CallbackQuery, db_user=None) -> None:
    recipient_id = int(query.data.split(":")[-1])
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        from app.repository import get_user_by_telegram_id
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.answer("User not found.", show_alert=True)
            return
        r = await get_recipient(session, recipient_id, user.id)
        if not r:
            await query.message.edit_text("Recipient not found.", reply_markup=back_keyboard("menu:recipients"))
            await query.answer()
            return

        from app.carriers import get_carrier
        carrier_obj = get_carrier(r.carrier)
        carrier_name = carrier_obj.display_name if carrier_obj else r.carrier

        text = (
            f"👤 <b>{r.name}</b>\n\n"
            f"Phone: {r.phone_e164}\n"
            f"Carrier: {carrier_name}\n"
            f"Gateway: <code>{r.gateway_email}</code>\n"
            f"Consented: {'✅' if r.consent_confirmed else '❌'}\n"
            f"Opted out: {'⛔ Yes' if r.is_opted_out else 'No'}\n"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⛔ Mark as Opted Out", callback_data=f"recipient:optout:{r.id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:recipients")],
        ])
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("recipient:optout:"))
async def cb_optout_recipient(query: CallbackQuery, db_user=None) -> None:
    recipient_id = int(query.data.split(":")[-1])
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        from app.repository import get_user_by_telegram_id
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.answer("User not found.", show_alert=True)
            return
        r = await get_recipient(session, recipient_id, user.id)
        if r:
            await opt_out_recipient(session, r, user, reason="Marked opted out via bot")
            await add_audit_log(
                session, AuditAction.RECIPIENT_OPTOUT, user,
                f"Opted out recipient {r.name} ({r.phone_e164})"
            )
            await query.message.edit_text(
                f"⛔ {r.name} has been marked as opted out. No further messages will be sent to them.",
                reply_markup=back_keyboard("menu:recipients"),
            )
        else:
            await query.message.edit_text("Recipient not found.", reply_markup=back_keyboard("menu:recipients"))
    await query.answer()
