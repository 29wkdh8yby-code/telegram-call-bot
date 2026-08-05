"""Common keyboards and message text helpers."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📨 Send Message", callback_data="menu:send"),
            InlineKeyboardButton(text="➕ Add Recipient", callback_data="menu:add_recipient"),
        ],
        [
            InlineKeyboardButton(text="👥 My Recipients", callback_data="menu:recipients"),
            InlineKeyboardButton(text="📊 Daily Usage", callback_data="menu:usage"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Account Settings", callback_data="menu:settings"),
            InlineKeyboardButton(text="❓ Help", callback_data="menu:help"),
        ],
    ])


def cancel_keyboard(back_data: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Back", callback_data=back_data),
            InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
        ]
    ])


def back_keyboard(back_data: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data=back_data)]
    ])


def yes_no_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes", callback_data=yes_data),
            InlineKeyboardButton(text="❌ No", callback_data=no_data),
        ]
    ])
