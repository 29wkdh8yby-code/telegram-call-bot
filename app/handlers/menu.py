"""Main menu, /start, /help handlers."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.keyboards import main_menu_keyboard

logger = structlog.get_logger(__name__)
router = Router(name="menu")

WELCOME_TEXT = (
    "👋 Welcome to the SMTP-to-SMS Notification Bot!\n\n"
    "This bot lets you send consent-based SMS notifications via your own email (SMTP) account "
    "to recipients who have opted in.\n\n"
    "⚠️ <b>Important:</b> SMS delivery is controlled by mobile carriers and is not guaranteed. "
    "Only send to recipients who have explicitly agreed to receive messages.\n\n"
    "Choose an option below:"
)

HELP_TEXT = (
    "<b>How to get started:</b>\n\n"
    "1️⃣ Go to <b>Account Settings</b> → <b>SMTP Account</b> and add your email credentials.\n"
    "2️⃣ Test the connection to verify it works.\n"
    "3️⃣ Go to <b>Add Recipient</b> and enter a phone number with consent confirmation.\n"
    "4️⃣ Use <b>Send Message</b> to compose and send.\n\n"
    "<b>Daily limit:</b> 250 messages per day (resets at midnight in your configured timezone).\n\n"
    "<b>Carrier SMS gateways</b> are email addresses that carriers provide for SMS delivery. "
    "Messages may be delayed, filtered, or blocked by carriers at any time.\n\n"
    "<b>Opt-out:</b> If a recipient wants to stop receiving messages, use "
    "<b>My Recipients</b> → select recipient → <b>Mark as Opted Out</b>."
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db_user=None) -> None:
    await state.clear()
    name = ""
    if db_user:
        name = db_user.first_name or db_user.username or ""
    greeting = f"Hello {name}! " if name else ""
    await message.answer(
        greeting + WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.message.edit_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(query: CallbackQuery) -> None:
    from app.handlers.keyboards import back_keyboard
    await query.message.edit_text(HELP_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
    await query.answer()
