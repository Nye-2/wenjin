from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.task.tasks import credit_periodic


@pytest.mark.asyncio
async def test_periodic_rules_skip_when_lock_is_held() -> None:
    fake_lock = SimpleNamespace(
        acquire=AsyncMock(return_value=False),
        owned=AsyncMock(return_value=False),
        release=AsyncMock(),
    )
    fake_redis = SimpleNamespace(
        is_connected=True,
        client=SimpleNamespace(lock=Mock(return_value=fake_lock)),
        connect=AsyncMock(),
        disconnect=AsyncMock(),
    )

    with (
        patch.object(credit_periodic, "RedisClient", return_value=fake_redis),
        patch.object(
            credit_periodic,
            "_process_periodic_rules_inner",
            AsyncMock(),
        ) as inner,
    ):
        result = await credit_periodic._process_periodic_rules()

    assert result == {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    fake_lock.acquire.assert_awaited_once_with(blocking=False)
    inner.assert_not_awaited()
    fake_lock.release.assert_not_awaited()
    fake_redis.disconnect.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_periodic_rules_release_lock_after_run() -> None:
    fake_lock = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        owned=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    fake_redis = SimpleNamespace(
        is_connected=True,
        client=SimpleNamespace(lock=Mock(return_value=fake_lock)),
        connect=AsyncMock(),
        disconnect=AsyncMock(),
    )
    summary = {"rules_evaluated": 1, "rules_fired": 1, "users_granted": 3}

    with (
        patch.object(credit_periodic, "RedisClient", return_value=fake_redis),
        patch.object(
            credit_periodic,
            "_process_periodic_rules_inner",
            AsyncMock(return_value=summary),
        ) as inner,
    ):
        result = await credit_periodic._process_periodic_rules()

    assert result == summary
    fake_lock.acquire.assert_awaited_once_with(blocking=False)
    inner.assert_awaited_once_with()
    fake_lock.owned.assert_awaited_once_with()
    fake_lock.release.assert_awaited_once_with()
    fake_redis.disconnect.assert_awaited_once_with()
