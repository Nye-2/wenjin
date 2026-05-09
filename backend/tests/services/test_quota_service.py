"""Tests for QuotaService using mocked Redis."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.quota_service import QuotaExceeded, QuotaService, QuotaUsage


def _make_redis() -> AsyncMock:
    """Create a mock Redis client with in-memory state."""
    store: dict[str, int] = {}

    redis = AsyncMock()

    async def get(key):
        return str(store[key]) if key in store else None

    async def incrby(key, amount):
        store[key] = store.get(key, 0) + amount
        return store[key]

    async def decrby(key, amount):
        store[key] = max(0, store.get(key, 0) - amount)
        return store[key]

    async def expire(key, ttl):
        pass

    redis.get = AsyncMock(side_effect=get)
    redis.incrby = AsyncMock(side_effect=incrby)
    redis.decrby = AsyncMock(side_effect=decrby)
    redis.expire = AsyncMock(side_effect=expire)
    return redis


@pytest.mark.asyncio
async def test_check_under_limit():
    """check() returns True when usage is under the limit."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=1000)
    result = await svc.check("user-1", kind="tokens_daily", amount=500)
    assert result is True


@pytest.mark.asyncio
async def test_consume_increments():
    """consume() increments usage; get_usage reflects the consumed amount."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=1_000_000)
    await svc.consume("user-1", kind="tokens_daily", amount=5000)
    usage = await svc.get_usage("user-1")
    assert usage.tokens_daily == 5000


@pytest.mark.asyncio
async def test_check_over_limit():
    """check() returns False when usage would exceed the limit."""
    redis = _make_redis()
    svc = QuotaService(redis, daily_token_limit=100)
    # Consume up to the limit
    redis_data = {}

    # Directly set up the state: simulate 90 tokens already used
    redis2 = AsyncMock()

    store = {"quota:user-1:tokens_daily:20260509": "90"}

    async def get(key):
        return store.get(key)

    async def incrby(key, amount):
        store[key] = str(int(store.get(key, "0")) + amount)
        return int(store[key])

    async def decrby(key, amount):
        store[key] = str(max(0, int(store.get(key, "0")) - amount))
        return int(store[key])

    async def expire(key, ttl):
        pass

    redis2.get = AsyncMock(side_effect=get)
    redis2.incrby = AsyncMock(side_effect=incrby)
    redis2.decrby = AsyncMock(side_effect=decrby)
    redis2.expire = AsyncMock(side_effect=expire)

    svc2 = QuotaService(redis2, daily_token_limit=100)
    result = await svc2.check("user-1", kind="tokens_daily", amount=20)
    assert result is False
