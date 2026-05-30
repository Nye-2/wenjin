"""Celery worker configuration and entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any

from celery.signals import worker_process_init, worker_process_shutdown

from src.config.app_config import celery_settings, settings
from src.task.celery_app import celery_app

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from src.academic.cache.redis_client import RedisClient
    from src.config.extensions_config import ExtensionsConfig
    from src.mcp.manager import MCPManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

_worker_runner: asyncio.Runner | None = None


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
    parsed = parser.parse_args(argv)
    parsed.queues = [
        queue.strip()
        for queue in str(parsed.queues or "").split(",")
        if queue.strip()
    ]
    return parsed


type InitSentryFn = Callable[[], None]
type GetExtensionsConfigFn = Callable[[], "ExtensionsConfig"]
type ActivateMcpRuntimeFn = Callable[
    ...,
    Awaitable[tuple["MCPManager", list["BaseTool"]]],
]
type ShutdownMcpRuntimeFn = Callable[[], Awaitable[None]]


async def _maybe_call_async_method(target: object, method_name: str, **kwargs: object) -> None:
    """Call an optional async method when the runtime object implements it."""
    method = getattr(target, method_name, None)
    if method is None:
        return
    await method(**kwargs)


def _load_worker_runtime_dependencies() -> tuple[
    InitSentryFn,
    RedisClient,
    GetExtensionsConfigFn,
    ActivateMcpRuntimeFn,
]:
    """Load bootstrap-time dependencies lazily to keep imports localized."""
    from src.academic.cache.redis_client import redis_client
    from src.config import get_extensions_config
    from src.mcp import activate_mcp_runtime
    from src.observability.sentry import init_sentry

    return (
        init_sentry,
        redis_client,
        get_extensions_config,
        activate_mcp_runtime,
    )


def _load_worker_shutdown_dependencies() -> tuple[
    ShutdownMcpRuntimeFn,
    RedisClient,
]:
    """Load shutdown-time dependencies lazily."""
    from src.academic.cache.redis_client import redis_client
    from src.mcp import shutdown_mcp_runtime

    return shutdown_mcp_runtime, redis_client


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


async def _bootstrap_worker_runtime() -> None:
    """Initialize worker-process runtime dependencies before task execution."""
    (
        init_sentry,
        redis_client,
        get_extensions_config,
        activate_mcp_runtime,
    ) = _load_worker_runtime_dependencies()

    init_sentry()
    await redis_client.reset_client(close_current=False)
    await _maybe_call_async_method(
        redis_client,
        "reset_stream_client",
        close_current=False,
    )
    await redis_client.connect()
    await _maybe_call_async_method(redis_client, "connect_stream")
    manager, _ = await activate_mcp_runtime(
        extensions_config=get_extensions_config(),
        warmup=True,
    )
    runtime_errors = manager.get_last_load_errors()
    if runtime_errors:
        if settings.mcp_required_for_worker_bootstrap:
            raise RuntimeError(
                f"MCP runtime bootstrap failed for worker process: {runtime_errors}"
            )
        logger.warning(
            "Worker MCP runtime degraded; continuing without MCP tools: %s",
            runtime_errors,
        )


async def _shutdown_worker_runtime() -> None:
    """Release worker-process runtime dependencies."""
    shutdown_mcp_runtime, redis_client = _load_worker_shutdown_dependencies()

    try:
        await shutdown_mcp_runtime()
    finally:
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
        _run_async(_bootstrap_worker_runtime())
        logger.info("Worker process runtime bootstrap completed")
    except Exception:
        logger.exception("Worker process runtime bootstrap failed")
        raise


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
) -> None:
    """Start a Celery worker.

    Args:
        concurrency: Number of worker processes/threads
        loglevel: Logging level (debug, info, warning, error)
        queues: List of queues to consume (default: all queues)
    """
    from src.observability.prometheus import (
        prepare_worker_prometheus,
        start_worker_prometheus_server,
    )

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
    start_worker(concurrency=args.concurrency, queues=args.queues or None)
