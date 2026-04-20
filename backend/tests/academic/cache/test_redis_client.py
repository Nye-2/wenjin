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


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_reset_client_clears_cached_client_without_closing_when_requested(self):
        redis = AsyncMock()

        client = RedisClient(url="redis://test")
        client._client = redis

        await client.reset_client(close_current=False)

        assert client._client is None
        redis.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_rebuilds_client_after_process_fork(self, monkeypatch):
        first_client = AsyncMock()
        second_client = AsyncMock()
        second_client.ping = AsyncMock(return_value=True)
        build_calls: list[str] = []

        client = RedisClient(url="redis://test")
        client._client = first_client
        client._owner_pid = 100

        monkeypatch.setattr("src.academic.cache.redis_client.os.getpid", lambda: 200)
        monkeypatch.setattr(
            client,
            "_build_client",
            lambda: build_calls.append("build") or second_client,
        )

        await client.connect()

        assert build_calls == ["build"]
        assert client._client is second_client
        second_client.ping.assert_awaited_once()

    def test_build_stream_client_uses_stream_socket_timeout(self, monkeypatch):
        captured_kwargs: dict[str, object] = {}

        def _fake_from_url(_url: str, **kwargs: object):
            captured_kwargs.update(kwargs)
            return object()

        monkeypatch.setattr(
            "src.academic.cache.redis_client.redis.from_url",
            _fake_from_url,
        )

        client = RedisClient(url="redis://test")
        monkeypatch.setattr(
            client._settings,
            "stream_socket_timeout_seconds",
            17.0,
        )

        client._build_stream_client()

        assert captured_kwargs.get("socket_timeout") == 17.0
