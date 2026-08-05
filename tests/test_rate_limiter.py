"""Tests for rate limiter (using fakeredis)."""
from __future__ import annotations

import pytest
import pytest_asyncio


@pytest.fixture()
def patch_redis(monkeypatch):
    """Replace the real Redis client with fakeredis."""
    try:
        import fakeredis.aioredis as fakeredis
    except ImportError:
        pytest.skip("fakeredis not installed")

    fake = fakeredis.FakeRedis(decode_responses=True)
    import app.services.rate_limiter as rl
    monkeypatch.setattr(rl, "_redis", fake)
    return fake


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "123")
    monkeypatch.setenv("MINUTE_MESSAGE_LIMIT", "3")
    monkeypatch.setenv("HOURLY_MESSAGE_LIMIT", "10")
    monkeypatch.setenv("DAILY_MESSAGE_LIMIT", "20")
    from app.config import get_settings
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_first_message_allowed(patch_redis):
    from app.services.rate_limiter import check_and_increment
    allowed, reason = await check_and_increment(999)
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_minute_rate_limit_exceeded(patch_redis):
    from app.services.rate_limiter import check_and_increment
    for _ in range(3):
        await check_and_increment(888)
    allowed, reason = await check_and_increment(888)
    assert allowed is False
    assert "minute" in reason.lower()
