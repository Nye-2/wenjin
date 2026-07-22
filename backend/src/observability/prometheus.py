"""Prometheus metrics collection and exposure."""

import logging
import os
import shutil
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import Response

from src.config.app_config import get_prometheus_settings

logger = logging.getLogger(__name__)

# Lazy-initialized metrics (only created when Prometheus is enabled)
_http_requests_total: Any | None = None
_http_request_duration_seconds: Any | None = None
_active_tasks_gauge: Any | None = None
_task_duration_seconds: Any | None = None
_run_dispatch_total: Any | None = None
_run_wait_seconds: Any | None = None
_run_wait_polls: Any | None = None
_mission_queue_wait_seconds: Any | None = None
_mission_slice_duration_seconds: Any | None = None
_mission_slices_total: Any | None = None
_mission_lease_events_total: Any | None = None
_mission_dispatch_events_total: Any | None = None
_mission_reconciliation_total: Any | None = None
_mission_subagent_capacity_total: Any | None = None
_worker_metrics_server_started = False
_worker_metrics_lock = threading.Lock()

_MISSION_QUEUE_WAIT_BUCKETS = (
    0.1,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    180.0,
    300.0,
    600.0,
    900.0,
)
_MISSION_SLICE_DURATION_BUCKETS = (
    0.1,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    180.0,
    210.0,
    225.0,
)


def _prometheus_multiproc_dir() -> str | None:
    """Return the effective Prometheus multiprocess directory, if configured."""
    env_value = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if env_value is not None:
        normalized = env_value.strip()
        return normalized or None

    settings_value = getattr(get_prometheus_settings(), "multiproc_dir", "")
    if not isinstance(settings_value, str):
        return None
    settings_value = settings_value.strip()
    return settings_value or None


def _build_metrics_registry() -> Any:
    """Return the registry used to expose metrics for the current process."""
    multiproc_dir = _prometheus_multiproc_dir()
    if multiproc_dir:
        from prometheus_client import CollectorRegistry, multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return registry

    from prometheus_client import REGISTRY

    return REGISTRY


def _init_metrics() -> None:
    """Initialize Prometheus metric objects (idempotent)."""
    global _http_requests_total, _http_request_duration_seconds
    global _active_tasks_gauge, _task_duration_seconds
    global _run_dispatch_total, _run_wait_seconds, _run_wait_polls
    global _mission_queue_wait_seconds, _mission_slice_duration_seconds
    global _mission_slices_total, _mission_lease_events_total
    global _mission_dispatch_events_total, _mission_reconciliation_total
    global _mission_subagent_capacity_total

    if _http_requests_total is not None:
        return

    from prometheus_client import Counter, Gauge, Histogram

    _http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path_template", "status"],
    )
    _http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path_template"],
    )
    if _prometheus_multiproc_dir():
        _active_tasks_gauge = Gauge(
            "active_tasks_total",
            "Currently running async tasks",
            multiprocess_mode="livesum",
        )
    else:
        _active_tasks_gauge = Gauge(
            "active_tasks_total",
            "Currently running async tasks",
        )
    _task_duration_seconds = Histogram(
        "task_duration_seconds",
        "Task execution duration in seconds",
        ["task_type"],
    )
    _run_dispatch_total = Counter(
        "run_dispatch_total",
        "Total run dispatch attempts",
        ["result"],
    )
    _run_wait_seconds = Histogram(
        "run_wait_seconds",
        "Run wait/join duration in seconds",
        ["outcome"],
    )
    _run_wait_polls = Histogram(
        "run_wait_polls",
        "Number of poll iterations used to resolve run wait",
        ["outcome"],
    )
    _mission_queue_wait_seconds = Histogram(
        "mission_queue_wait_seconds",
        "Mission delivery wait after its scheduled availability",
        buckets=_MISSION_QUEUE_WAIT_BUCKETS,
    )
    _mission_slice_duration_seconds = Histogram(
        "mission_slice_duration_seconds",
        "Mission slice execution duration",
        ["outcome"],
        buckets=_MISSION_SLICE_DURATION_BUCKETS,
    )
    _mission_slices_total = Counter(
        "mission_slices_total",
        "Mission slices by bounded outcome and reason",
        ["outcome", "reason"],
    )
    _mission_lease_events_total = Counter(
        "mission_lease_events_total",
        "Mission lease and delivery fence events",
        ["result"],
    )
    _mission_dispatch_events_total = Counter(
        "mission_dispatch_events_total",
        "Mission dispatch reservation and publication events",
        ["result"],
    )
    _mission_reconciliation_total = Counter(
        "mission_reconciliation_total",
        "Mission reconciliation outcomes",
        ["result"],
    )
    _mission_subagent_capacity_total = Counter(
        "mission_subagent_capacity_total",
        "Global subagent capacity acquisition outcomes",
        ["result"],
    )


def get_path_template(request: Request) -> str:
    """Extract the route path template instead of the actual path."""
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            return path
    return request.url.path


async def prometheus_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Collect HTTP request metrics."""
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    path_template = get_path_template(request)
    request_counter = _http_requests_total
    duration_histogram = _http_request_duration_seconds
    if request_counter is None or duration_histogram is None:
        return response

    request_counter.labels(
        method=method, path_template=path_template, status=response.status_code
    ).inc()
    duration_histogram.labels(
        method=method, path_template=path_template
    ).observe(duration)

    return response


def setup_prometheus(app: FastAPI) -> None:
    """Set up Prometheus metrics collection and /metrics endpoint."""
    prometheus_settings = get_prometheus_settings()
    if not prometheus_settings.enabled:
        logger.info("Prometheus disabled, skipping setup")
        return

    _init_metrics()

    # Register HTTP metrics middleware
    app.middleware("http")(prometheus_middleware)

    # Mount /metrics endpoint
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(
            content=generate_latest(_build_metrics_registry()),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics")


def prepare_worker_prometheus() -> None:
    """Prepare worker-side Prometheus state before Celery forks child processes."""
    prometheus_settings = get_prometheus_settings()
    if not prometheus_settings.enabled:
        return

    multiproc_dir = _prometheus_multiproc_dir()
    if multiproc_dir:
        target_dir = Path(multiproc_dir).expanduser().resolve()
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(target_dir)
        logger.info("Prepared worker Prometheus multiprocess dir: %s", target_dir)

    _init_metrics()


def start_worker_prometheus_server() -> None:
    """Expose Celery worker metrics over HTTP for Prometheus scraping."""
    global _worker_metrics_server_started

    prometheus_settings = get_prometheus_settings()
    if not prometheus_settings.enabled:
        return

    with _worker_metrics_lock:
        if _worker_metrics_server_started:
            return

        from prometheus_client import start_http_server

        start_http_server(
            port=prometheus_settings.worker_port,
            addr="0.0.0.0",
            registry=_build_metrics_registry(),
        )
        _worker_metrics_server_started = True
        logger.info(
            "Worker Prometheus metrics enabled on 0.0.0.0:%s",
            prometheus_settings.worker_port,
        )


def mark_worker_process_dead(pid: int | None = None) -> None:
    """Mark a Prometheus multiprocess worker child as dead."""
    if not _prometheus_multiproc_dir():
        return

    try:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(pid or os.getpid())  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to mark Prometheus worker process dead", exc_info=True)


# Public helpers for task-level instrumentation
def track_task_start() -> None:
    """Increment active tasks gauge."""
    if _active_tasks_gauge is not None:
        _active_tasks_gauge.inc()


def track_task_end(task_type: str, duration: float) -> None:
    """Decrement active tasks gauge and record task duration."""
    if _active_tasks_gauge is not None:
        _active_tasks_gauge.dec()
    if _task_duration_seconds is not None:
        _task_duration_seconds.labels(task_type=task_type).observe(duration)


def track_run_dispatch(result: str) -> None:
    """Increment run dispatch counter by result."""
    if _run_dispatch_total is not None:
        _run_dispatch_total.labels(result=result).inc()


def observe_run_wait(outcome: str, duration: float, polls: int) -> None:
    """Record run wait duration and polling effort."""
    if _run_wait_seconds is not None:
        _run_wait_seconds.labels(outcome=outcome).observe(max(0.0, float(duration)))
    if _run_wait_polls is not None:
        _run_wait_polls.labels(outcome=outcome).observe(max(0, int(polls)))


def observe_mission_queue_wait(duration: float) -> None:
    if _mission_queue_wait_seconds is not None:
        _mission_queue_wait_seconds.observe(max(0.0, float(duration)))


def track_mission_slice(*, outcome: str, reason: str, duration: float) -> None:
    if _mission_slice_duration_seconds is not None:
        _mission_slice_duration_seconds.labels(outcome=outcome).observe(
            max(0.0, float(duration))
        )
    if _mission_slices_total is not None:
        _mission_slices_total.labels(outcome=outcome, reason=reason).inc()
    if reason in {
        "delivery_expired",
        "lease_fence_lost",
        "lease_not_acquired",
        "stale_delivery",
    } and _mission_lease_events_total is not None:
        _mission_lease_events_total.labels(result=reason).inc()


def track_mission_dispatch(result: str) -> None:
    if _mission_dispatch_events_total is not None:
        _mission_dispatch_events_total.labels(result=result).inc()


def track_mission_reconciliation(result: str) -> None:
    if _mission_reconciliation_total is not None:
        _mission_reconciliation_total.labels(result=result).inc()


def track_mission_subagent_capacity(result: str) -> None:
    if _mission_subagent_capacity_total is not None:
        _mission_subagent_capacity_total.labels(result=result).inc()
