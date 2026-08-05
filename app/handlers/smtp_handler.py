"""SMTP account management handlers."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import get_session_factory
from app.handlers.keyboards import back_keyboard, cancel_keyboard
from app.models import AuditAction, SmtpEncryption
from app.repository import (
    add_audit_log,
    create_smtp_account,
    get_smtp_accounts,
    verify_smtp_account,
)
from app.services.smtp_service import SmtpConfig, test_smtp_connection

logger = structlog.get_logger(__name__)
router = Router(name="smtp")


class SmtpSetupStates(StatesGroup):
    label = State()
    host = State()
    port = State()
    username = State()
    smtp_pass = State()
    encryption = State()
    sender_name = State()
    confirm = State()


@router.callback_query(F.data == "settings:smtp_add")
async def cb_smtp_add_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SmtpSetupStates.label)
    await query.message.edit_text(
        "📧 <b>Add SMTP Account</b>\n\nEnter a label for this account (e.g. <i>Gmail Work</i>):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )
    await query.answer()


@router.message(SmtpSetupStates.label)
async def smtp_got_label(message: Message, state: FSMContext) -> None:
    label = message.text.strip() if message.text else ""
    if not label:
        await message.answer("Please enter a label.")
        return
    await state.update_data(label=label)
    await state.set_state(SmtpSetupStates.host)
    await message.answer(
        "Enter the SMTP host:\n(e.g. <code>smtp.gmail.com</code>, <code>smtp.office365.com</code>, "
        "<code>smtp.zoho.com</code>)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )


@router.message(SmtpSetupStates.host)
async def smtp_got_host(message: Message, state: FSMContext) -> None:
    host = (message.text or "").strip()
    if not host:
        await message.answer("Please enter a valid hostname.")
        return
    await state.update_data(host=host)
    await state.set_state(SmtpSetupStates.port)
    await message.answer(
        "Enter the SMTP port:\n(Common: <code>587</code> for TLS, <code>465</code> for SSL, <code>25</code>)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )


@router.message(SmtpSetupStates.port)
async def smtp_got_port(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 65535):
        await message.answer("Please enter a valid port number (1-65535).")
        return
    await state.update_data(port=int(text))
    await state.set_state(SmtpSetupStates.username)
    await message.answer(
        "Enter your SMTP username/email address:",
        reply_markup=cancel_keyboard("menu:settings"),
    )


@router.message(SmtpSetupStates.username)
async def smtp_got_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if "@" not in username:
        await message.answer("Please enter a valid email address.")
        return
    await state.update_data(username=username)
    await state.set_state(SmtpSetupStates.smtp_pass)
    await message.answer(
        "Enter your SMTP password or app password:\n"
        "🔒 This will be <b>encrypted</b> and never shown again in full.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )


@router.message(SmtpSetupStates.smtp_pass)
async def smtp_got_pass(message: Message, state: FSMContext) -> None:
    smtp_pass = (message.text or "").strip()
    if not smtp_pass:
        await message.answer("Password cannot be empty.")
        return
    # Delete the message containing the password for security
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(smtp_pass=smtp_pass)
    await state.set_state(SmtpSetupStates.encryption)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="TLS (port 587)", callback_data="smtp_enc:TLS"),
            InlineKeyboardButton(text="SSL (port 465)", callback_data="smtp_enc:SSL"),
        ],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:settings")],
    ])
    await message.answer("Select encryption type:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("smtp_enc:"))
async def smtp_got_encryption(query: CallbackQuery, state: FSMContext) -> None:
    enc = query.data.split(":")[1]
    await state.update_data(encryption=enc)
    await state.set_state(SmtpSetupStates.sender_name)
    await query.message.edit_text(
        "Enter the sender name recipients will see in their SMS:\n"
        "(e.g. <i>My Business</i> — leave blank to use your email address)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )
    await query.answer()


@router.message(SmtpSetupStates.sender_name)
async def smtp_got_sender_name(message: Message, state: FSMContext) -> None:
    sender_name = (message.text or "").strip() or None
    await state.update_data(sender_name=sender_name)
    data = await state.get_data()

    masked = "*" * min(len(data.get("smtp_pass", "")), 8)
    summary = (
        f"📧 <b>Review SMTP Account</b>\n\n"
        f"Label: {data['label']}\n"
        f"Host: {data['host']}:{data['port']}\n"
        f"Username: {data['username']}\n"
        f"Password: {masked}\n"
        f"Encryption: {data['encryption']}\n"
        f"Sender name: {data.get('sender_name') or data['username']}\n\n"
        "Save and test this SMTP connection?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Save & Test", callback_data="smtp_confirm:save"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="menu:settings"),
        ]
    ])
    await state.set_state(SmtpSetupStates.confirm)
    await message.answer(summary, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "smtp_confirm:save")
async def smtp_save_and_test(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    data = await state.get_data()
    await state.clear()

    if db_user is None:
        await query.answer("Session expired. Please /start again.", show_alert=True)
        return

    await query.message.edit_text("🔄 Testing SMTP connection…")

    config = SmtpConfig(
        host=data["host"],
        port=data["port"],
        username=data["username"],
        smtp_password=data["smtp_pass"],
        encryption=SmtpEncryption(data["encryption"]),
        sender_name=data.get("sender_name"),
    )

    success, msg = await test_smtp_connection(config)

    factory = get_session_factory()
    async with factory() as session:
        account = await create_smtp_account(
            session,
            user=db_user,
            label=data["label"],
            host=data["host"],
            port=data["port"],
            username=data["username"],
            password_plaintext=data["smtp_pass"],
            encryption=data["encryption"],
            sender_name=data.get("sender_name"),
        )
        if success:
            await verify_smtp_account(session, account)
            await add_audit_log(session, AuditAction.SMTP_ADD, db_user, f"SMTP {data['host']} added and verified")
            await query.message.edit_text(
                f"✅ SMTP account <b>{data['label']}</b> saved and verified!\n\n{msg}",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:settings"),
            )
        else:
            await add_audit_log(session, AuditAction.SMTP_ADD, db_user, f"SMTP {data['host']} saved (test failed)")
            await query.message.edit_text(
                f"⚠️ SMTP account saved but connection test failed:\n<code>{msg}</code>\n\n"
                "You can still use it, but messages may not send. Check your credentials.",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:settings"),
            )

    await query.answer()
