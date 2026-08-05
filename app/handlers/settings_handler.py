"""Account settings handlers: SMTP management, sender name, usage."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import get_session_factory
from app.handlers.keyboards import back_keyboard, cancel_keyboard
from app.repository import (
    get_smtp_accounts,
    get_user_by_telegram_id,
    update_sender_name,
)
from app.services.rate_limiter import get_daily_usage

logger = structlog.get_logger(__name__)
router = Router(name="settings")

SETTINGS_TEXT = (
    "⚙️ <b>Account Settings</b>\n\n"
    "Manage your SMTP accounts and display name."
)


class SettingsStates(StatesGroup):
    sender_name = State()


@router.callback_query(F.data == "menu:settings")
async def cb_settings(query: CallbackQuery, db_user=None) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 SMTP Accounts", callback_data="settings:smtp_list")],
        [InlineKeyboardButton(text="✏️ Set Sender Name", callback_data="settings:sender_name")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:main")],
    ])
    await query.message.edit_text(SETTINGS_TEXT, reply_markup=keyboard, parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data == "settings:smtp_list")
async def cb_smtp_list(query: CallbackQuery, db_user=None) -> None:
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        accounts = await get_smtp_accounts(session, user) if user else []

    if not accounts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add SMTP Account", callback_data="settings:smtp_add")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:settings")],
        ])
        await query.message.edit_text(
            "📧 No SMTP accounts yet. Add one to start sending.",
            reply_markup=keyboard,
        )
        await query.answer()
        return

    buttons = []
    for a in accounts:
        status = "✅" if a.is_verified else "⚠️"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {a.label} ({a.username})",
            callback_data=f"settings:smtp_view:{a.id}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Add SMTP Account", callback_data="settings:smtp_add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:settings")])

    await query.message.edit_text(
        "📧 <b>Your SMTP Accounts</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(F.data.startswith("settings:smtp_view:"))
async def cb_smtp_view(query: CallbackQuery, db_user=None) -> None:
    account_id = int(query.data.split(":")[-1])
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.answer("User not found.", show_alert=True)
            return
        from app.repository import get_smtp_account
        account = await get_smtp_account(session, account_id, user.id)
        if not account:
            await query.message.edit_text("Account not found.", reply_markup=back_keyboard("settings:smtp_list"))
            await query.answer()
            return

        text = (
            f"📧 <b>{account.label}</b>\n\n"
            f"Host: {account.host}:{account.port}\n"
            f"Username: {account.username}\n"
            f"Password: {'*' * 8} (encrypted)\n"
            f"Encryption: {account.encryption.value}\n"
            f"Sender name: {account.sender_name or account.username}\n"
            f"Verified: {'✅' if account.is_verified else '❌'}\n"
            f"Active: {'✅' if account.is_active else '❌'}\n"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Re-test Connection", callback_data=f"settings:smtp_retest:{account.id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="settings:smtp_list")],
        ])
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("settings:smtp_retest:"))
async def cb_smtp_retest(query: CallbackQuery, db_user=None) -> None:
    account_id = int(query.data.split(":")[-1])
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return

    await query.message.edit_text("🔄 Testing SMTP connection…")

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if not user:
            await query.message.edit_text("User not found.")
            return
        from app.repository import get_smtp_account, verify_smtp_account, get_plain_password
        account = await get_smtp_account(session, account_id, user.id)
        if not account:
            await query.message.edit_text("Account not found.")
            return

        from app.services.smtp_service import SmtpConfig, test_smtp_connection
        config = SmtpConfig(
            host=account.host,
            port=account.port,
            username=account.username,
            smtp_password=get_plain_password(account),
            encryption=account.encryption,
            sender_name=account.sender_name,
        )
        success, msg = await test_smtp_connection(config)
        if success:
            await verify_smtp_account(session, account)
            await query.message.edit_text(
                f"✅ Connection test successful!\n{msg}",
                reply_markup=back_keyboard("settings:smtp_list"),
            )
        else:
            await query.message.edit_text(
                f"❌ Connection test failed:\n{msg}",
                reply_markup=back_keyboard("settings:smtp_list"),
            )
    await query.answer()


@router.callback_query(F.data == "settings:sender_name")
async def cb_set_sender_name(query: CallbackQuery, state: FSMContext, db_user=None) -> None:
    current = db_user.sender_name if db_user else None
    await state.set_state(SettingsStates.sender_name)
    await query.message.edit_text(
        f"✏️ Enter your sender name:\n"
        f"(Current: <code>{current or 'Not set'}</code>)\n\n"
        "This name may appear in messages sent to recipients.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("menu:settings"),
    )
    await query.answer()


@router.message(SettingsStates.sender_name)
async def settings_got_sender_name(message: Message, state: FSMContext, db_user=None) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Name cannot be empty.")
        return
    await state.clear()
    if db_user is None:
        await message.answer("Session expired.")
        return

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, db_user.telegram_id)
        if user:
            await update_sender_name(session, user, name)

    await message.answer(
        f"✅ Sender name set to: <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=back_keyboard("menu:settings"),
    )


@router.callback_query(F.data == "menu:usage")
async def cb_daily_usage(query: CallbackQuery, db_user=None) -> None:
    if db_user is None:
        await query.answer("Session expired.", show_alert=True)
        return
    used, limit = await get_daily_usage(db_user.telegram_id)
    remaining = limit - used
    bar_filled = int((used / limit) * 20) if limit > 0 else 0
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    text = (
        f"📊 <b>Daily Usage</b>\n\n"
        f"[{bar}]\n\n"
        f"Sent Today: <b>{used}</b> / {limit}\n"
        f"Remaining Today: <b>{remaining}</b>\n\n"
        "Limit resets at midnight in your configured timezone."
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=back_keyboard())
    await query.answer()
