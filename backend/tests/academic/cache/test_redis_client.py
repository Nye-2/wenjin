"""Tests for RedisClient lock safety."""

from unittest.mock import AsyncMock

import pytest

from src.academic.cache.redis_client import RedisClient


class TestWorkspaceLock:
    @pytest.mark.asyncio
    async def test_workspace_lock_releases_with_token_check(self):
        """Lock release should verify ownership token before deleting."""
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.eval = AsyncMock(return_value=1)

        client = RedisClient(url="redis://test")
        client._client = redis

        async with client.workspace_lock("ws-1", timeout=30):
            pass

        redis.set.assert_called_once()
        _, token = redis.set.await_args.args[0], redis.set.await_args.args[1]
        redis.eval.assert_called_once()
        eval_args = redis.eval.await_args.args
        assert eval_args[1] == 1
        assert eval_args[2] == "lock:workspace:ws-1:write"
        assert eval_args[3] == token

    @pytest.mark.asyncio
    async def test_workspace_lock_raises_when_not_acquired(self):
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=False)

        client = RedisClient(url="redis://test")
        client._client = redis

        with pytest.raises(RuntimeError, match="Could not acquire lock"):
            async with client.workspace_lock("ws-1", timeout=30):
                pass
