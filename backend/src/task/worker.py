"""Celery worker configuration and entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from celery.signals import worker_process_init, worker_process_shutdown

from src.config.app_config import celery_settings
from src.task.celery_app import celery_app

if TYPE_CHECKING:
    from src.academic.cache.redis_client import RedisClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

_worker_runner: asyncio.Runner | None = None
_require_mission_model_profile = False

WORKER_READINESS_FILE = Path("/tmp/wenjin-worker-ready")


def parse_worker_cli_args(argv: list[str]) -> argparse.Namespace:
    """Parse worker startup arguments for Docker and local entrypoints."""
    parser = argparse.ArgumentParser(description="Start a Wenjin Celery worker")
    parser.add_argument(
        "concurrency",
        nargs="?",
        type=int,
        default=celery_settings.worker_concurrency,
    )
    parser.add_argument(
        "--queues",
        default="",
        help="Comma-separated Celery queues to consume.",
    )
    parser.add_argument(
        "--prefetch-multiplier",
        type=int,
        default=None,
        help="Per-worker prefetch override; mission workers must use 1.",
    )
    parser.add_argument(
        "--require-mission-model-profile",
        action="store_true",
        help="Fail startup unless the canonical Mission model profile is usable.",
    )
    parsed = parser.parse_args(argv)
    parsed.queues = [
        queue.strip()
        for queue in str(parsed.queues or "").split(",")
        if queue.strip()
    ]
    return parsed


type InitSentryFn = Callable[[], None]


async def _maybe_call_async_method(target: object, method_name: str, **kwargs: object) -> None:
    """Call an optional async method when the runtime object implements it."""
    method = getattr(target, method_name, None)
    if method is None:
        return
    await method(**kwargs)


def _load_worker_runtime_dependencies() -> tuple[
    InitSentryFn,
    RedisClient,
]:
    """Load bootstrap-time dependencies lazily to keep imports localized."""
    from src.academic.cache.redis_client import redis_client
    from src.observability.sentry import init_sentry

    return init_sentry, redis_client


def _load_worker_shutdown_dependencies() -> RedisClient:
    """Load shutdown-time dependencies lazily."""
    from src.academic.cache.redis_client import redis_client
    return redis_client


def _get_worker_runner() -> asyncio.Runner:
    """Return the process-local asyncio runner used by Celery tasks and hooks."""
    global _worker_runner
    if _worker_runner is None:
        _worker_runner = asyncio.Runner()
    return _worker_runner


def close_worker_runner() -> None:
    """Close and clear the process-local asyncio runner."""
    global _worker_runner
    if _worker_runner is None:
        return

    _worker_runner.close()
    _worker_runner = None


def _worker_readiness_file() -> Path:
    configured = os.environ.get("WORKER_READINESS_FILE", "").strip()
    return Path(configured) if configured else WORKER_READINESS_FILE


def _clear_worker_readiness() -> None:
    _worker_readiness_file().unlink(missing_ok=True)


def _mark_worker_ready(*, mission_model_id: str | None = None) -> None:
    marker = mission_model_id or "ready"
    _worker_readiness_file().write_text(f"{marker}\n", encoding="utf-8")


def _validate_default_mission_model_profile() -> str:
    from src.mission_runtime.production import require_mission_model_profile
    from src.services.model_catalog_cache import get_default_runtime_model_id

    model_id = get_default_runtime_model_id()
    require_mission_model_profile(model_id)
    return model_id


async def _bootstrap_worker_runtime(*, require_mission_model_profile: bool = False) -> None:
    """Initialize worker-process runtime dependencies before task execution."""
    init_sentry, redis_client = _load_worker_runtime_dependencies()

    init_sentry()
    await redis_client.reset_client(close_current=False)
    await _maybe_call_async_method(
        redis_client,
        "reset_stream_client",
        close_current=False,
    )
    await redis_client.connect()
    await _maybe_call_async_method(redis_client, "connect_stream")
    try:
        await _refresh_worker_model_catalog_cache()
    except Exception as exc:
        if require_mission_model_profile:
            raise RuntimeError(
                "Canonical Mission model catalog warmup failed"
            ) from exc
        logger.warning(
            "Worker model catalog runtime cache warmup skipped: %s",
            exc,
            exc_info=True,
        )
    if require_mission_model_profile:
        _validate_default_mission_model_profile()
async def _refresh_worker_model_catalog_cache() -> None:
    """Warm the worker-process model catalog cache from DataService."""
    from src.dataservice_client.provider import dataservice_client
    from src.task.model_catalog_runtime import refresh_runtime_model_catalog

    async with dataservice_client() as dataservice:
        await refresh_runtime_model_catalog(
            dataservice,
            logger=logger,
            context="Worker model catalog runtime",
        )


async def _shutdown_worker_runtime() -> None:
    """Release worker-process runtime dependencies."""
    redis_client = _load_worker_shutdown_dependencies()
    await redis_client.disconnect()


def _run_async(coro: Coroutine[Any, Any, object]) -> None:
    """Run an async coroutine on the worker process runner."""
    _get_worker_runner().run(coro)


def run_worker_coroutine[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine on the shared worker process loop."""
    return _get_worker_runner().run(coro)


def _on_worker_process_init(**_kwargs: object) -> None:
    """Bootstrap runtime inside each Celery worker process."""
    try:
        _run_async(
            _bootstrap_worker_runtime(
                require_mission_model_profile=_require_mission_model_profile,
            )
        )
        _mark_worker_ready(
            mission_model_id=(
                _validate_default_mission_model_profile()
                if _require_mission_model_profile
                else None
            )
        )
        logger.info("Worker process runtime bootstrap completed")
    except Exception as exc:
        _clear_worker_readiness()
        logger.exception("Worker process runtime bootstrap failed")
        # Celery's signal dispatcher catches Exception, so use SystemExit to
        # prevent a bootstrap-failed process from consuming queued work.
        raise SystemExit(1) from exc


def _on_worker_process_shutdown(**_kwargs: object) -> None:
    """Best-effort runtime shutdown for each Celery worker process."""
    try:
        _run_async(_shutdown_worker_runtime())
    except Exception:
        logger.warning("Worker process runtime shutdown failed", exc_info=True)
    finally:
        try:
            from src.observability.prometheus import mark_worker_process_dead

            mark_worker_process_dead()
        except Exception:
            logger.warning("Failed to update Prometheus worker state", exc_info=True)
        close_worker_runner()


worker_process_init.connect(_on_worker_process_init)
worker_process_shutdown.connect(_on_worker_process_shutdown)


def start_worker(
    concurrency: int | None = None,
    loglevel: str = "info",
    queues: list[str] | None = None,
    prefetch_multiplier: int | None = None,
    require_mission_model_profile: bool = False,
) -> None:
    """Start a Celery worker.

    Args:
        concurrency: Number of worker processes/threads
        loglevel: Logging level (debug, info, warning, error)
        queues: List of queues to consume (default: all queues)
        prefetch_multiplier: Optional worker-specific prefetch override.
    """
    global _require_mission_model_profile

    from src.observability.prometheus import (
        prepare_worker_prometheus,
        start_worker_prometheus_server,
    )

    _require_mission_model_profile = require_mission_model_profile
    _clear_worker_readiness()
    prepare_worker_prometheus()
    start_worker_prometheus_server()

    concurrency = concurrency or celery_settings.worker_concurrency
    worker_pool = str(celery_settings.worker_pool or "solo").strip() or "solo"
    if concurrency < 1:
        concurrency = 1
    if worker_pool == "solo" and concurrency != 1:
        logger.info(
            "Celery pool=solo ignores >1 concurrency; coercing concurrency %s -> 1",
            concurrency,
        )
        concurrency = 1
    logger.info(
        "Starting Celery worker with concurrency=%s, pool=%s, loglevel=%s",
        concurrency,
        worker_pool,
        loglevel,
    )

    argv: list[str] = [
        "worker",
        f"--concurrency={concurrency}",
        f"--pool={worker_pool}",
        f"--loglevel={loglevel}",
        "--without-gossip",
        "--without-mingle",
    ]

    if queues:
        argv.extend(["-Q", ",".join(queues)])
    if prefetch_multiplier is not None:
        if prefetch_multiplier < 1:
            raise ValueError("prefetch_multiplier must be at least 1")
        argv.append(f"--prefetch-multiplier={prefetch_multiplier}")

    celery_app.worker_main(argv=argv)


def start_flower(port: int = 5555) -> None:
    """Start Flower (Celery monitoring UI).

    Args:
        port: Port to run Flower on
    """
    import subprocess

    logger.info(f"Starting Flower on port {port}")
    subprocess.run(["celery", "-A", "src.task.celery_app", "flower", f"--port={port}"])


if __name__ == "__main__":
    args = parse_worker_cli_args(sys.argv[1:])
    start_worker(
        concurrency=args.concurrency,
        queues=args.queues or None,
        prefetch_multiplier=args.prefetch_multiplier,
        require_mission_model_profile=args.require_mission_model_profile,
    )
