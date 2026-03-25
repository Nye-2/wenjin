"""Tests for Celery worker runtime lifecycle hooks."""

from __future__ import annotations

import asyncio

import pytest

from src.task import worker as worker_module


@pytest.mark.asyncio
async def test_bootstrap_worker_runtime_raises_on_mcp_validation_errors(monkeypatch):
    init_calls: list[str] = []

    class FakeManager:
        def get_last_load_errors(self):
            return {"secure-http": "401 unauthorized"}

    async def _fake_activate_mcp_runtime(**_kwargs):
        return FakeManager(), []

    async def _fake_reset_db_engine(*, dispose_current=True):
        init_calls.append(f"reset_db:{dispose_current}")

    async def _fake_init_db():
        init_calls.append("db")

    class FakeRedisClient:
        async def reset_client(self, *, close_current=True):
            init_calls.append(f"reset_redis:{close_current}")

        async def connect(self):
            init_calls.append("redis")

    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: init_calls.append("sentry"),
            _fake_reset_db_engine,
            _fake_init_db,
            FakeRedisClient(),
            lambda: object(),
            _fake_activate_mcp_runtime,
        ),
    )

    with pytest.raises(RuntimeError, match="secure-http"):
        await worker_module._bootstrap_worker_runtime()

    assert init_calls == [
        "sentry",
        "reset_db:False",
        "reset_redis:False",
        "db",
        "redis",
    ]


def test_run_worker_coroutine_reuses_process_runner():
    async def _current_loop():
        return asyncio.get_running_loop()

    first_loop = worker_module.run_worker_coroutine(_current_loop())
    second_loop = worker_module.run_worker_coroutine(_current_loop())

    try:
        assert first_loop is second_loop
    finally:
        worker_module.close_worker_runner()
