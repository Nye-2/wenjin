"""Prometheus metrics collection and exposure."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.responses import Response

from src.config.app_config import get_prometheus_settings

logger = logging.getLogger(__name__)

# Lazy-initialized metrics (only created when Prometheus is enabled)
_http_requests_total = None
_http_request_duration_seconds = None
_active_tasks_gauge = None
_task_duration_seconds = None


def _init_metrics():
    """Initialize Prometheus metric objects (idempotent)."""
    global _http_requests_total, _http_request_duration_seconds
    global _active_tasks_gauge, _task_duration_seconds

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
    _active_tasks_gauge = Gauge(
        "active_tasks_total",
        "Currently running async tasks",
    )
    _task_duration_seconds = Histogram(
        "task_duration_seconds",
        "Task execution duration in seconds",
        ["task_type"],
    )


def get_path_template(request: Request) -> str:
    """Extract the route path template instead of the actual path."""
    route = request.scope.get("route")
    if route and hasattr(route, "path"):
        return route.path
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
    _http_requests_total.labels(
        method=method, path_template=path_template, status=response.status_code
    ).inc()
    _http_request_duration_seconds.labels(
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
    async def metrics_endpoint():
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics")


# Public helpers for task-level instrumentation
def track_task_start():
    """Increment active tasks gauge."""
    if _active_tasks_gauge is not None:
        _active_tasks_gauge.inc()


def track_task_end(task_type: str, duration: float):
    """Decrement active tasks gauge and record task duration."""
    if _active_tasks_gauge is not None:
        _active_tasks_gauge.dec()
    if _task_duration_seconds is not None:
        _task_duration_seconds.labels(task_type=task_type).observe(duration)
