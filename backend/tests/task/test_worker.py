"""Tests for Celery worker runtime lifecycle hooks."""

from __future__ import annotations

import asyncio

import pytest

from src.task import worker as worker_module


@pytest.mark.asyncio
async def test_bootstrap_worker_runtime_degrades_on_mcp_validation_errors(monkeypatch):
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

        async def reset_stream_client(self, *, close_current=True):
            init_calls.append(f"reset_redis_stream:{close_current}")

        async def connect(self):
            init_calls.append("redis")

        async def connect_stream(self):
            init_calls.append("redis_stream")

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
    monkeypatch.setattr(
        worker_module.settings,
        "mcp_required_for_worker_bootstrap",
        False,
    )

    await worker_module._bootstrap_worker_runtime()

    assert init_calls == [
        "sentry",
        "reset_db:False",
        "reset_redis:False",
        "reset_redis_stream:False",
        "db",
        "redis",
        "redis_stream",
    ]


@pytest.mark.asyncio
async def test_bootstrap_worker_runtime_raises_in_strict_mcp_mode(monkeypatch):
    class FakeManager:
        def get_last_load_errors(self):
            return {"secure-http": "401 unauthorized"}

    async def _fake_activate_mcp_runtime(**_kwargs):
        return FakeManager(), []

    async def _fake_reset_db_engine(*, dispose_current=True):
        return None

    async def _fake_init_db():
        return None

    class FakeRedisClient:
        async def reset_client(self, *, close_current=True):
            return None

        async def reset_stream_client(self, *, close_current=True):
            return None

        async def connect(self):
            return None

        async def connect_stream(self):
            return None

    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: None,
            _fake_reset_db_engine,
            _fake_init_db,
            FakeRedisClient(),
            lambda: object(),
            _fake_activate_mcp_runtime,
        ),
    )
    monkeypatch.setattr(
        worker_module.settings,
        "mcp_required_for_worker_bootstrap",
        True,
    )

    with pytest.raises(RuntimeError, match="secure-http"):
        await worker_module._bootstrap_worker_runtime()


def test_run_worker_coroutine_reuses_process_runner():
    async def _current_loop():
        return asyncio.get_running_loop()

    first_loop = worker_module.run_worker_coroutine(_current_loop())
    second_loop = worker_module.run_worker_coroutine(_current_loop())

    try:
        assert first_loop is second_loop
    finally:
        worker_module.close_worker_runner()


def test_start_worker_coerces_solo_pool_concurrency(monkeypatch):
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "src.observability.prometheus.prepare_worker_prometheus",
        lambda: None,
    )
    monkeypatch.setattr(
        "src.observability.prometheus.start_worker_prometheus_server",
        lambda: None,
    )
    monkeypatch.setattr(worker_module.celery_settings, "worker_pool", "solo")
    monkeypatch.setattr(
        worker_module.celery_app,
        "worker_main",
        lambda argv: calls.append(list(argv)),
    )

    worker_module.start_worker(concurrency=4, loglevel="warning")

    assert len(calls) == 1
    assert "--concurrency=1" in calls[0]
    assert "--pool=solo" in calls[0]


def test_parse_worker_cli_args_accepts_queue_list():
    args = worker_module.parse_worker_cli_args(["2", "--queues", "long_running,default"])

    assert args.concurrency == 2
    assert args.queues == ["long_running", "default"]
