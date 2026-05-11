"""Tests for QuotaService using mocked Redis."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.quota_service import QuotaExceeded, QuotaService, QuotaUsage


def _make_redis() -> AsyncMock:
    """Create a mock Redis client with in-memory state implementing Lua eval."""
    store: dict[str, int] = {}

    redis = AsyncMock()

    async def get(key):
        return str(store[key]) if key in store else None

    async def decrby(key, amount):
        store[key] = max(0, store.get(key, 0) - amount)
        return store[key]

    async def eval_lua(script, num_keys, key, limit, amount, ttl):
        """Simulate the Lua check-and-increment atomically in Python."""
        current = store.get(key, 0)
        if current + amount <= limit:
            store[key] = current + amount
            return store[key]
        return -1

    redis.get = AsyncMock(side_effect=get)
    redis.decrby = AsyncMock(side_effect=decrby)
    redis.eval = AsyncMock(side_effect=eval_lua)
    return redis


@pytest.mark.asyncio
async def test_check_under_limit():
    """check() returns True when usage is under the limit (read-only inspection)."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=1000)
    result = await svc.check("user-1", kind="tokens_daily", amount=500)
    assert result is True


@pytest.mark.asyncio
async def test_consume_increments():
    """consume() atomically increments usage; get_usage reflects the consumed amount."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=1_000_000)
    new_val = await svc.consume("user-1", kind="tokens_daily", amount=5000)
    assert new_val == 5000
    usage = await svc.get_usage("user-1")
    assert usage.tokens_daily == 5000


@pytest.mark.asyncio
async def test_consume_raises_on_over_limit():
    """consume() raises QuotaExceeded directly when limit would be exceeded."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=100)
    # Consume 90 tokens first
    await svc.consume("user-1", kind="tokens_daily", amount=90)
    # Attempting 20 more should exceed the limit of 100
    with pytest.raises(QuotaExceeded):
        await svc.consume("user-1", kind="tokens_daily", amount=20)


@pytest.mark.asyncio
async def test_check_over_limit():
    """check() returns False when usage would exceed the limit."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=100)

    store: dict[str, int] = {}
    redis2 = AsyncMock()

    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw_store = {f"quota:user-1:tokens_daily:{day}": "90"}

    async def get(key):
        return raw_store.get(key)

    async def eval_lua(script, num_keys, key, limit, amount, ttl):
        current = int(raw_store.get(key, "0"))
        if current + amount <= limit:
            raw_store[key] = str(current + amount)
            return current + amount
        return -1

    redis2.get = AsyncMock(side_effect=get)
    redis2.eval = AsyncMock(side_effect=eval_lua)

    svc2 = QuotaService(redis2, daily_token_limit=100)
    result = await svc2.check("user-1", kind="tokens_daily", amount=20)
    assert result is False
