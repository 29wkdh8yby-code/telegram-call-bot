"""Admin command handlers."""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.database import get_session_factory
from app.models import AuditAction
from app.repository import (
    add_audit_log,
    count_failed_today,
    count_messages_today,
    count_total_users,
    get_audit_logs,
    get_user_by_telegram_id,
    list_all_users,
    set_user_daily_limit,
    suspend_user,
)
from app.services.rate_limiter import get_daily_usage

logger = structlog.get_logger(__name__)
router = Router(name="admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_settings().admin_telegram_ids


def _admin_required(func):
    """Decorator that returns a 403 if caller is not admin."""
    import functools

    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        from_user = getattr(event, "from_user", None) or getattr(event, "effective_user", None)
        if from_user is None and hasattr(event, "message"):
            from_user = event.message.from_user
        uid = from_user.id if from_user else None
        if not uid or not _is_admin(uid):
            if isinstance(event, Message):
                await event.answer("⛔ Admin only.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Admin only.", show_alert=True)
            return
        return await func(event, *args, **kwargs)

    return wrapper


@router.message(Command("admin"))
@_admin_required
async def cmd_admin(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 System Stats", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👥 Users", callback_data="admin:users")],
        [InlineKeyboardButton(text="📜 Audit Logs", callback_data="admin:audit")],
    ])
    await message.answer("🔐 <b>Admin Panel</b>", reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin:stats")
@_admin_required
async def admin_stats(query: CallbackQuery) -> None:
    factory = get_session_factory()
    async with factory() as session:
        total_users = await count_total_users(session)
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        msgs_today = await count_messages_today(session, today_str)
        failed_today = await count_failed_today(session)

    text = (
        f"📊 <b>System Stats</b>\n\n"
        f"Total Users: {total_users}\n"
        f"Messages Today: {msgs_today}\n"
        f"Failed Today: {failed_today}\n"
    )
    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:main")]
        ]),
    )
    await query.answer()


@router.callback_query(F.data == "admin:main")
@_admin_required
async def admin_main(query: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 System Stats", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👥 Users", callback_data="admin:users")],
        [InlineKeyboardButton(text="📜 Audit Logs", callback_data="admin:audit")],
    ])
    await query.message.edit_text("🔐 <b>Admin Panel</b>", reply_markup=keyboard, parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data == "admin:users")
@_admin_required
async def admin_users(query: CallbackQuery) -> None:
    factory = get_session_factory()
    async with factory() as session:
        users = await list_all_users(session)

    if not users:
        await query.message.edit_text("No users yet.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:main")]
        ]))
        await query.answer()
        return

    buttons = []
    for u in users[:20]:
        name = u.first_name or u.username or str(u.telegram_id)
        status = "🚫" if u.is_suspended else "✅"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {name}",
            callback_data=f"admin:user:{u.telegram_id}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin:main")])

    await query.message.edit_text(
        "👥 <b>Users</b> (latest 20):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(F.data.startswith("admin:user:"))
@_admin_required
async def admin_view_user(query: CallbackQuery) -> None:
    target_tid = int(query.data.split(":")[-1])
    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, target_tid)
        if not user:
            await query.message.edit_text("User not found.")
            await query.answer()
            return

        used, limit = await get_daily_usage(target_tid)
        text = (
            f"👤 <b>User</b>\n\n"
            f"Telegram ID: {user.telegram_id}\n"
            f"Name: {user.first_name} {user.last_name or ''}\n"
            f"Username: @{user.username or '-'}\n"
            f"Status: {'🚫 Suspended' if user.is_suspended else '✅ Active'}\n"
            f"Daily limit: {user.daily_limit_override or limit} (default: {limit})\n"
            f"Usage today: {used} / {user.daily_limit_override or limit}\n"
            f"Joined: {user.created_at.strftime('%Y-%m-%d')}\n"
        )

        action_btn = "admin:unsuspend" if user.is_suspended else "admin:suspend"
        action_label = "✅ Unsuspend" if user.is_suspended else "🚫 Suspend"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=action_label, callback_data=f"{action_btn}:{user.telegram_id}")],
            [InlineKeyboardButton(text="⚙️ Change Daily Limit", callback_data=f"admin:setlimit:{user.telegram_id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:users")],
        ])
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("admin:suspend:"))
@_admin_required
async def admin_suspend_user(query: CallbackQuery) -> None:
    target_tid = int(query.data.split(":")[-1])
    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, target_tid)
        if user:
            await suspend_user(session, user, True)
            admin_user = await get_user_by_telegram_id(session, query.from_user.id)
            await add_audit_log(session, AuditAction.ADMIN_SUSPEND, admin_user, f"Suspended user {target_tid}")
    await query.answer("User suspended.", show_alert=True)
    await admin_view_user(query)


@router.callback_query(F.data.startswith("admin:unsuspend:"))
@_admin_required
async def admin_unsuspend_user(query: CallbackQuery) -> None:
    target_tid = int(query.data.split(":")[-1])
    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_telegram_id(session, target_tid)
        if user:
            await suspend_user(session, user, False)
            admin_user = await get_user_by_telegram_id(session, query.from_user.id)
            await add_audit_log(session, AuditAction.ADMIN_UNSUSPEND, admin_user, f"Unsuspended user {target_tid}")
    await query.answer("User unsuspended.", show_alert=True)
    await admin_view_user(query)


@router.callback_query(F.data == "admin:audit")
@_admin_required
async def admin_audit(query: CallbackQuery) -> None:
    factory = get_session_factory()
    async with factory() as session:
        logs = await get_audit_logs(session, limit=20)

    if not logs:
        await query.message.edit_text("No audit logs.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:main")]
        ]))
        await query.answer()
        return

    lines = ["📜 <b>Recent Audit Logs</b>\n"]
    for log in logs:
        ts = log.created_at.strftime("%m/%d %H:%M")
        lines.append(f"{ts} | {log.action.value} | uid={log.user_id} | {(log.detail or '')[:60]}")

    await query.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:main")]
        ]),
    )
    await query.answer()
