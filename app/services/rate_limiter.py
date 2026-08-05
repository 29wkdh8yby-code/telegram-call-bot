"""
Redis-backed rate limiting for per-user message sending.

Keys used:
  smsbot:rl:{telegram_id}:minute   → count, TTL 60s
  smsbot:rl:{telegram_id}:hour     → count, TTL 3600s
  smsbot:rl:{telegram_id}:day:{YYYY-MM-DD} → count, TTL 86400s
"""
from __future__ import annotations

from datetime import datetime

import pytz
import redis.asyncio as aioredis

from app.config import get_settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _today_str() -> str:
    settings = get_settings()
    tz = pytz.timezone(settings.app_timezone)
    return datetime.now(tz).strftime("%Y-%m-%d")


async def check_and_increment(telegram_id: int) -> tuple[bool, str]:
    """
    Check rate limits and increment counters if allowed.

    Returns (allowed, reason_if_denied).
    """
    r = get_redis()
    settings = get_settings()

    uid = str(telegram_id)
    today = _today_str()

    minute_key = f"smsbot:rl:{uid}:minute"
    hour_key = f"smsbot:rl:{uid}:hour"
    day_key = f"smsbot:rl:{uid}:day:{today}"

    pipe = r.pipeline()
    pipe.get(minute_key)
    pipe.get(hour_key)
    pipe.get(day_key)
    results = await pipe.execute()

    minute_count = int(results[0] or 0)
    hour_count = int(results[1] or 0)
    day_count = int(results[2] or 0)

    if minute_count >= settings.minute_message_limit:
        return False, f"Rate limit: max {settings.minute_message_limit} messages per minute."
    if hour_count >= settings.hourly_message_limit:
        return False, f"Rate limit: max {settings.hourly_message_limit} messages per hour."
    if day_count >= settings.daily_message_limit:
        return False, f"Daily limit reached: {settings.daily_message_limit} messages per day."

    # Increment all three counters
    pipe = r.pipeline()
    pipe.incr(minute_key)
    pipe.expire(minute_key, 60)
    pipe.incr(hour_key)
    pipe.expire(hour_key, 3600)
    pipe.incr(day_key)
    pipe.expire(day_key, 86400 + 3600)  # extra hour buffer
    await pipe.execute()

    return True, ""


async def get_daily_usage(telegram_id: int) -> tuple[int, int]:
    """Return (used_today, daily_limit)."""
    r = get_redis()
    settings = get_settings()

    today = _today_str()
    day_key = f"smsbot:rl:{str(telegram_id)}:day:{today}"
    count = int((await r.get(day_key)) or 0)
    return count, settings.daily_message_limit


async def reset_daily_usage(telegram_id: int) -> None:
    """Admin helper: reset today's count for a user."""
    r = get_redis()
    today = _today_str()
    day_key = f"smsbot:rl:{str(telegram_id)}:day:{today}"
    await r.delete(day_key)
