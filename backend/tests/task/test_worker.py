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
        "_refresh_worker_model_catalog_cache",
        lambda: _append_async(init_calls, "model_catalog"),
    )
    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: init_calls.append("sentry"),
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
        "reset_redis:False",
        "reset_redis_stream:False",
        "redis",
        "redis_stream",
        "model_catalog",
    ]


@pytest.mark.asyncio
async def test_bootstrap_worker_runtime_raises_in_strict_mcp_mode(monkeypatch):
    class FakeManager:
        def get_last_load_errors(self):
            return {"secure-http": "401 unauthorized"}

    async def _fake_activate_mcp_runtime(**_kwargs):
        return FakeManager(), []

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
        "_refresh_worker_model_catalog_cache",
        lambda: _noop_async(),
    )
    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: None,
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


@pytest.mark.asyncio
async def test_bootstrap_worker_runtime_degrades_on_model_catalog_warmup_errors(monkeypatch):
    init_calls: list[str] = []

    class FakeManager:
        def get_last_load_errors(self):
            return {}

    async def _fake_activate_mcp_runtime(**_kwargs):
        return FakeManager(), []

    class FakeRedisClient:
        async def reset_client(self, *, close_current=True):
            init_calls.append(f"reset_redis:{close_current}")

        async def reset_stream_client(self, *, close_current=True):
            init_calls.append(f"reset_redis_stream:{close_current}")

        async def connect(self):
            init_calls.append("redis")

        async def connect_stream(self):
            init_calls.append("redis_stream")

    async def _raise_refresh():
        raise RuntimeError("dataservice unavailable")

    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: init_calls.append("sentry"),
            FakeRedisClient(),
            lambda: object(),
            _fake_activate_mcp_runtime,
        ),
    )
    monkeypatch.setattr(worker_module, "_refresh_worker_model_catalog_cache", _raise_refresh)

    await worker_module._bootstrap_worker_runtime()

    assert init_calls == [
        "sentry",
        "reset_redis:False",
        "reset_redis_stream:False",
        "redis",
        "redis_stream",
    ]


@pytest.mark.asyncio
async def test_mission_worker_bootstrap_fails_closed_on_catalog_warmup_error(monkeypatch):
    async def _raise_refresh():
        raise RuntimeError("dataservice unavailable")

    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: None,
            _ConnectedRedisClient(),
            lambda: object(),
            lambda **_kwargs: _noop_async(),
        ),
    )
    monkeypatch.setattr(worker_module, "_refresh_worker_model_catalog_cache", _raise_refresh)

    with pytest.raises(RuntimeError, match="catalog warmup failed"):
        await worker_module._bootstrap_worker_runtime(require_mission_model_profile=True)


@pytest.mark.asyncio
async def test_mission_worker_bootstrap_validates_canonical_profile(monkeypatch):
    validated: list[str] = []

    class FakeManager:
        def get_last_load_errors(self):
            return {}

    async def _activate(**_kwargs):
        return FakeManager(), []

    monkeypatch.setattr(
        worker_module,
        "_load_worker_runtime_dependencies",
        lambda: (
            lambda: None,
            _ConnectedRedisClient(),
            lambda: object(),
            _activate,
        ),
    )
    monkeypatch.setattr(worker_module, "_refresh_worker_model_catalog_cache", _noop_async)
    monkeypatch.setattr(
        worker_module,
        "_validate_default_mission_model_profile",
        lambda: validated.append("gpt-5.6-sol") or "gpt-5.6-sol",
    )

    await worker_module._bootstrap_worker_runtime(require_mission_model_profile=True)

    assert validated == ["gpt-5.6-sol"]


def test_worker_process_exits_when_runtime_bootstrap_fails(monkeypatch):
    readiness_cleared: list[bool] = []

    def _raise_bootstrap(_coro):
        _coro.close()
        raise RuntimeError("invalid model profile")

    monkeypatch.setattr(worker_module, "_run_async", _raise_bootstrap)
    monkeypatch.setattr(
        worker_module,
        "_clear_worker_readiness",
        lambda: readiness_cleared.append(True),
    )

    with pytest.raises(SystemExit) as exc_info:
        worker_module._on_worker_process_init()

    assert exc_info.value.code == 1
    assert readiness_cleared == [True]


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


def test_parse_worker_cli_args_accepts_queue_list_and_prefetch_override():
    args = worker_module.parse_worker_cli_args(
        [
            "2",
            "--queues",
            "long_running,default",
            "--prefetch-multiplier",
            "1",
            "--require-mission-model-profile",
        ]
    )

    assert args.concurrency == 2
    assert args.queues == ["long_running", "default"]
    assert args.prefetch_multiplier == 1
    assert args.require_mission_model_profile is True


def test_start_worker_applies_mission_prefetch_override(monkeypatch):
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

    worker_module.start_worker(
        concurrency=1,
        queues=["long_running"],
        prefetch_multiplier=1,
    )

    assert "-Q" in calls[0]
    assert "long_running" in calls[0]
    assert "--prefetch-multiplier=1" in calls[0]


async def _append_async(calls: list[str], value: str) -> None:
    calls.append(value)


async def _noop_async() -> None:
    return None


class _ConnectedRedisClient:
    async def reset_client(self, *, close_current=True):
        return None

    async def reset_stream_client(self, *, close_current=True):
        return None

    async def connect(self):
        return None

    async def connect_stream(self):
        return None
