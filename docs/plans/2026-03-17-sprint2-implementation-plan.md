# Sprint 2: Observability Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Activate production observability (Sentry + Prometheus) and wire idle Redis cache functions to their intended callers.

**Architecture:** Three parallel tracks — (A) Sentry SDK init + error handler integration, (B) Prometheus metrics middleware + /metrics endpoint + Docker services, (C) Redis distributed lock + agent status in task execution.

**Tech Stack:** sentry-sdk[fastapi], prometheus-client, redis, FastAPI middleware, Docker Compose

---

## Task 1: Sentry Error Monitoring — Init Module + App Integration

**Files:**
- Create: `src/observability/__init__.py`
- Create: `src/observability/sentry.py`
- Modify: `src/gateway/app.py` (lifespan startup)
- Modify: `src/gateway/middleware/error_handler.py` (generic_exception_handler)
- Modify: `src/gateway/middleware/correlation.py` (set Sentry tag)
- Modify: `pyproject.toml` (add sentry-sdk dependency)
- Test: `tests/observability/test_sentry.py`

### Step 1: Add sentry-sdk dependency

In `pyproject.toml`, add to `dependencies` list:
```
"sentry-sdk[fastapi]>=2.0.0",
```

### Step 2: Create `src/observability/__init__.py`

```python
"""Observability package — Sentry + Prometheus integration."""
```

### Step 3: Create `src/observability/sentry.py`

```python
"""Sentry error monitoring initialization."""

import logging

from src.config.app_config import get_sentry_settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry SDK if enabled and DSN is configured."""
    sentry_settings = get_sentry_settings()
    if not sentry_settings.enabled or not sentry_settings.dsn:
        logger.info("Sentry disabled or DSN not configured, skipping init")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=sentry_settings.dsn,
        environment=sentry_settings.environment,
        traces_sample_rate=sentry_settings.traces_sample_rate,
        profiles_sample_rate=sentry_settings.profiles_sample_rate,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            RedisIntegration(),
        ],
    )
    logger.info("Sentry initialized (env=%s)", sentry_settings.environment)
```

### Step 4: Integrate into `src/gateway/app.py` lifespan

Add `init_sentry()` call as the first line inside lifespan startup (before logging setup):
```python
from src.observability.sentry import init_sentry
init_sentry()
```

### Step 5: Add `sentry_sdk.capture_exception` in error_handler.py

In `generic_exception_handler`, after the `logger.exception(...)` call, add:
```python
try:
    import sentry_sdk
    sentry_sdk.capture_exception(exc)
except Exception:
    pass
```

### Step 6: Set correlation_id as Sentry tag in correlation.py

In `correlation_middleware`, after `correlation_id_var.set(correlation_id)`, add:
```python
try:
    import sentry_sdk
    sentry_sdk.set_tag("correlation_id", correlation_id)
except Exception:
    pass
```

### Step 7: Write test `tests/observability/test_sentry.py`

```python
"""Tests for Sentry initialization."""

from unittest.mock import MagicMock, patch

from src.observability.sentry import init_sentry


class TestInitSentry:
    def test_skips_when_disabled(self):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(enabled=False, dsn="")
            # Should not raise
            init_sentry()

    def test_skips_when_no_dsn(self):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(enabled=True, dsn="")
            init_sentry()

    @patch("sentry_sdk.init")
    def test_initializes_when_enabled_with_dsn(self, mock_init):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                enabled=True,
                dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
                environment="test",
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
            )
            init_sentry()
            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args[1]
            assert call_kwargs["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
            assert call_kwargs["environment"] == "test"
```

### Step 8: Run tests

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/observability/test_sentry.py -v
```

### Step 9: Ruff check

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run ruff check src/observability/ src/gateway/app.py src/gateway/middleware/error_handler.py src/gateway/middleware/correlation.py
```

### Step 10: Commit

```bash
git add src/observability/ src/gateway/app.py src/gateway/middleware/error_handler.py src/gateway/middleware/correlation.py pyproject.toml tests/observability/
git commit -m "feat(observability): add Sentry error monitoring integration"
```

---

## Task 2: Prometheus Metrics — Middleware + /metrics Endpoint

**Files:**
- Create: `src/observability/prometheus.py`
- Modify: `src/gateway/app.py` (setup_prometheus call)
- Modify: `pyproject.toml` (add prometheus-client dependency)
- Test: `tests/observability/test_prometheus.py`

### Step 1: Add prometheus-client dependency

In `pyproject.toml`, add to `dependencies`:
```
"prometheus-client>=0.21.0",
```

### Step 2: Create `src/observability/prometheus.py`

```python
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
    """Initialize Prometheus metric objects."""
    global _http_requests_total, _http_request_duration_seconds
    global _active_tasks_gauge, _task_duration_seconds

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
    """Extract the route path template (e.g. /api/workspaces/{id}) instead of the actual path."""
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
    _http_requests_total.labels(method=method, path_template=path_template, status=response.status_code).inc()
    _http_request_duration_seconds.labels(method=method, path_template=path_template).observe(duration)

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
```

### Step 3: Integrate into `src/gateway/app.py`

After rate limiting setup, add:
```python
# Prometheus metrics
from src.observability.prometheus import setup_prometheus
setup_prometheus(app)
```

### Step 4: Write test `tests/observability/test_prometheus.py`

```python
"""Tests for Prometheus metrics integration."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSetupPrometheus:
    def test_skips_when_disabled(self):
        app = FastAPI()
        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=False)
            from src.observability.prometheus import setup_prometheus
            setup_prometheus(app)
        # /metrics should not exist
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_metrics_endpoint_available_when_enabled(self):
        app = FastAPI()
        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=True)
            from src.observability.prometheus import setup_prometheus
            setup_prometheus(app)
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text or "process_" in resp.text

    def test_http_metrics_collected(self):
        app = FastAPI()

        @app.get("/test-route")
        async def test_route():
            return {"ok": True}

        with patch("src.observability.prometheus.get_prometheus_settings") as mock:
            mock.return_value = MagicMock(enabled=True)
            from src.observability.prometheus import setup_prometheus
            setup_prometheus(app)

        client = TestClient(app)
        client.get("/test-route")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text


class TestTaskMetrics:
    def test_track_task_noop_when_not_initialized(self):
        from src.observability.prometheus import track_task_end, track_task_start
        # Should not raise when metrics are None
        track_task_start()
        track_task_end("test", 1.0)
```

### Step 5: Run tests

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/observability/test_prometheus.py -v
```

### Step 6: Ruff check

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run ruff check src/observability/prometheus.py
```

### Step 7: Commit

```bash
git add src/observability/prometheus.py src/gateway/app.py pyproject.toml tests/observability/test_prometheus.py
git commit -m "feat(observability): add Prometheus metrics middleware and /metrics endpoint"
```

---

## Task 3: Docker Compose — Prometheus + Grafana Services

**Files:**
- Modify: `docker-compose.yml` (root)
- Create: `monitoring/prometheus.yml`
- Create: `monitoring/grafana/provisioning/datasources/prometheus.yml`
- Create: `monitoring/grafana/provisioning/dashboards/dashboard.yml`
- Create: `monitoring/grafana/provisioning/dashboards/academiagpt.json`

### Step 1: Add Prometheus + Grafana to root docker-compose.yml

Add after the `nginx` service:

```yaml
  # Prometheus metrics collection
  prometheus:
    image: prom/prometheus:latest
    container_name: academiagpt-prometheus
    restart: unless-stopped
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    depends_on:
      gateway:
        condition: service_healthy
    networks:
      - academiagpt-network

  # Grafana dashboards
  grafana:
    image: grafana/grafana:latest
    container_name: academiagpt-grafana
    restart: unless-stopped
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on:
      - prometheus
    ports:
      - "3001:3000"
    networks:
      - academiagpt-network
```

Add volumes:
```yaml
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
```

### Step 2: Create `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "academiagpt-gateway"
    metrics_path: "/metrics"
    static_configs:
      - targets: ["gateway:8001"]
```

### Step 3: Create Grafana provisioning files

See implementation for datasource + dashboard provisioning YAML and JSON.

### Step 4: Commit

```bash
git add docker-compose.yml monitoring/
git commit -m "infra(monitoring): add Prometheus + Grafana to Docker Compose"
```

---

## Task 4: Redis Cache Wiring — workspace_lock in Feature Execution

**Files:**
- Modify: `src/application/handlers/feature_execution_handler.py`
- Test: `tests/application/handlers/test_feature_execution_handler.py` (add lock test)

### Step 1: Wire workspace_lock in FeatureExecutionHandler.execute()

Wrap the task submission section (steps 6-8) with `workspace_lock`:

In `execute()`, after step 5 (credit billing), before step 6 (build payload):
```python
# 5.5 Acquire workspace lock to prevent concurrent duplicate submissions
if redis_client:
    try:
        async with redis_client.workspace_lock(workspace_id, timeout=30):
            # re-check for active task inside lock
            existing = await self.task_service.find_active_task(
                user_id=str(self.user.id),
                task_type=feature.task_type,
                workspace_id=workspace_id,
                feature_id=feature_id,
                action=str(action) if action is not None else None,
            )
            if existing:
                return { ... idempotent response ... }
            # proceed with payload build + submit
    except RuntimeError:
        # Lock acquisition failed — another submission in progress
        return { ... concurrent warning ... }
```

NOTE: The design doc says to replace optimistic lock with distributed mutex. The current code already does an `find_active_task` check (step 4), but that's not atomic. We'll wrap the submit in a lock for safety.

### Step 2: Write test for workspace lock integration

Test that concurrent calls to execute with the same workspace_id are serialized.

### Step 3: Run tests

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/application/handlers/test_feature_execution_handler.py -v
```

### Step 4: Commit

```bash
git add src/application/handlers/feature_execution_handler.py tests/application/handlers/test_feature_execution_handler.py
git commit -m "feat(redis): wire workspace_lock for concurrent task submission guard"
```

---

## Task 5: Redis Cache Wiring — Agent Status in Task Execution

**Files:**
- Modify: `src/task/tasks/base.py` (set agent status on start/complete/fail)
- Modify: `src/task/executor.py` (LocalExecutor: set agent status)
- Test: `tests/task/test_agent_status.py`

### Step 1: Add agent status tracking in _execute_task_async

In `base.py`, after `mark_task_started`, add:
```python
thread_id = payload.get("thread_id")
if thread_id:
    await redis_client.set_agent_status(thread_id, "running", skill=task_type)
```

On success:
```python
if thread_id:
    await redis_client.set_agent_status(thread_id, "completed")
```

On failure:
```python
if thread_id:
    await redis_client.set_agent_status(thread_id, "failed")
```

### Step 2: Same for LocalExecutor._run_task_locally

Add same agent status tracking in `executor.py` `_run_task_locally()`.

### Step 3: Write test

### Step 4: Run tests and commit

```bash
git commit -m "feat(redis): wire agent status tracking in task execution"
```

---

## Task 6: Prometheus Task Metrics in Executor

**Files:**
- Modify: `src/task/executor.py` (import and use track_task_start/track_task_end)
- Modify: `src/task/tasks/base.py` (same)
- Test: `tests/task/test_executor.py` (verify metric calls)

### Step 1: Add task metrics instrumentation

In both `_execute_task_async` (base.py) and `_run_task_locally` (executor.py), wrap the execution with:
```python
from src.observability.prometheus import track_task_start, track_task_end
import time

track_task_start()
start_time = time.perf_counter()
try:
    ...  # existing logic
finally:
    duration = time.perf_counter() - start_time
    track_task_end(task_type, duration)
```

### Step 2: Run tests and commit

```bash
git commit -m "feat(observability): add Prometheus task execution metrics"
```

---

## Task 7: Integration Verification + Release Gate Update

**Files:**
- Modify: `src/services/release_gate_service.py` (add Sprint 2 checks)
- Run: Full regression suite

### Step 1: Add Sprint 2 checks to release gate

Add test entries for:
- `observability_sentry` → `tests/observability/test_sentry.py`
- `observability_prometheus` → `tests/observability/test_prometheus.py`

### Step 2: Run full regression

```bash
cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/observability/ tests/task/test_executor.py tests/task/test_service_executor.py tests/application/handlers/test_feature_execution_handler.py -v
```

### Step 3: Commit

```bash
git commit -m "chore(gate): add Sprint 2 observability checks to release gate"
```
