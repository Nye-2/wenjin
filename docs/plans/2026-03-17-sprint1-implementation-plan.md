# Sprint 1: Celery Dual-Mode Executor + Rate Limiting — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the broken task execution path when Celery is disabled and activate the idle rate limiting middleware.

**Architecture:** Introduce a `TaskExecutor` protocol with two implementations — `CeleryExecutor` (existing queue path) and `LocalExecutor` (asyncio in-process fallback). The service layer delegates to whichever is configured. Rate limiting is a one-line middleware registration.

**Tech Stack:** Python 3.13, FastAPI, asyncio, Celery, Redis, pytest

---

### Task 1: LocalExecutor — Failing Test

**Files:**
- Create: `backend/tests/task/test_executor.py`

**Step 1: Write the failing test for LocalExecutor**

```python
"""Tests for task executor abstraction."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis_client():
    client = AsyncMock()
    client.client = AsyncMock()
    client.client.hset = AsyncMock()
    client.client.expire = AsyncMock()
    client.client.publish = AsyncMock()
    client.client.hgetall = AsyncMock(return_value={})
    client._client = True  # pretend connected
    return client


class TestLocalExecutor:
    """Tests for in-process task execution when Celery is disabled."""

    @pytest.mark.asyncio
    async def test_execute_runs_task_in_background(self, mock_redis_client):
        """LocalExecutor should schedule task via asyncio.create_task."""
        from src.task.executor import LocalExecutor

        executor = LocalExecutor(max_concurrency=2)

        with patch("src.task.executor._run_task_locally", new_callable=AsyncMock) as mock_run:
            await executor.execute(
                task_id="test-task-1",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1"},
                queue="default",
            )
            # Give the background task a chance to start
            await asyncio.sleep(0.05)
            mock_run.assert_called_once_with("test-task-1", "workspace_feature", {"workspace_id": "ws-1"})

    @pytest.mark.asyncio
    async def test_execute_respects_semaphore(self):
        """LocalExecutor should limit concurrent executions."""
        from src.task.executor import LocalExecutor

        executor = LocalExecutor(max_concurrency=1)
        started = asyncio.Event()
        blocker = asyncio.Event()

        async def slow_task(task_id, task_type, payload):
            started.set()
            await blocker.wait()

        with patch("src.task.executor._run_task_locally", side_effect=slow_task):
            # Start first task — should acquire semaphore
            await executor.execute("t1", "workspace_feature", {}, "default")
            await started.wait()

            # Start second task — should be queued (not started yet)
            second_started = False

            async def mark_second(task_id, task_type, payload):
                nonlocal second_started
                second_started = True

            with patch("src.task.executor._run_task_locally", side_effect=mark_second):
                await executor.execute("t2", "workspace_feature", {}, "default")
                await asyncio.sleep(0.05)
                assert not second_started, "Second task should be blocked by semaphore"

            # Release first task
            blocker.set()
            await asyncio.sleep(0.05)


class TestCeleryExecutor:
    """Tests for Celery-based task execution."""

    @pytest.mark.asyncio
    async def test_execute_sends_to_celery(self):
        """CeleryExecutor should call celery_app.send_task."""
        from src.task.executor import CeleryExecutor

        mock_celery = MagicMock()
        executor = CeleryExecutor(celery_app=mock_celery)

        await executor.execute(
            task_id="test-task-1",
            task_type="workspace_feature",
            payload={"workspace_id": "ws-1"},
            queue="default",
        )

        mock_celery.send_task.assert_called_once_with(
            "src.task.tasks.execute_task",
            args=["test-task-1", "workspace_feature", {"workspace_id": "ws-1"}],
            queue="default",
            priority=5,
            task_id="test-task-1",
        )


class TestGetExecutor:
    """Tests for executor factory function."""

    def test_returns_celery_when_enabled(self):
        from src.task.executor import CeleryExecutor, get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = True
            executor = get_executor()
            assert isinstance(executor, CeleryExecutor)

    def test_returns_local_when_disabled(self):
        from src.task.executor import LocalExecutor, get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = False
            executor = get_executor()
            assert isinstance(executor, LocalExecutor)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.task.executor'`

---

### Task 2: LocalExecutor — Implementation

**Files:**
- Create: `backend/src/task/executor.py`

**Step 3: Write the executor module**

```python
"""Task executor abstraction — dual-mode (Celery / local asyncio)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)


class TaskExecutor(Protocol):
    """Protocol for task execution backends."""

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None: ...


class CeleryExecutor:
    """Submit tasks to Celery broker queue."""

    def __init__(self, celery_app=None):
        if celery_app is None:
            from src.task import celery_app as _app
            celery_app = _app
        self._celery_app = celery_app

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        self._celery_app.send_task(
            "src.task.tasks.execute_task",
            args=[task_id, task_type, payload],
            queue=queue,
            priority=priority,
            task_id=task_id,
        )


class LocalExecutor:
    """Execute tasks in-process via asyncio (dev / low-traffic fallback)."""

    def __init__(self, max_concurrency: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: dict,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        asyncio.create_task(self._guarded_run(task_id, task_type, payload))

    async def _guarded_run(self, task_id: str, task_type: str, payload: dict) -> None:
        async with self._semaphore:
            await _run_task_locally(task_id, task_type, payload)


async def _run_task_locally(task_id: str, task_type: str, payload: dict) -> None:
    """Run a task in the current process, reusing the Celery task logic."""
    from src.academic.cache.redis_client import redis_client
    from src.academic.services import ArtifactService
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    if redis_client._client is None:
        await redis_client.connect()

    progress = ProgressTracker(redis_client, task_id)

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        try:
            await store.mark_task_started(task_id, worker_id="local-executor")
            await progress.update(0, "Task started")

            from src.task.tasks.base import _dispatch_task

            result = await _dispatch_task(task_type, payload, progress)

            # Deep research artifact persistence (same as base.py)
            if task_type == "deep_research":
                artifacts = result.get("artifacts") or []
                if isinstance(artifacts, list) and artifacts:
                    service = ArtifactService(db)
                    workspace_id = str(payload.get("workspace_id") or "")
                    persisted_refs: list[dict] = []
                    for artifact in artifacts:
                        art_type = artifact.get("type", "other")
                        content = artifact.get("content", {}) or {}
                        title = artifact.get("title") or {
                            "literature_review": "Deep Research 文献综述",
                            "research_ideas": "Deep Research 研究创意",
                            "gap_analysis": "Deep Research 研究空白分析",
                        }.get(art_type, f"Deep Research {art_type}")
                        record = await service.create(
                            workspace_id=workspace_id,
                            type=art_type,
                            title=title,
                            content=content,
                            created_by_skill=artifact.get("created_by_skill") or "deep-research",
                        )
                        persisted_refs.append({"id": str(record.id), "type": record.type, "title": record.title or ""})
                    result["artifacts"] = persisted_refs
                    refresh_targets = result.get("refresh_targets") or []
                    if "artifacts" not in refresh_targets:
                        result["refresh_targets"] = [*refresh_targets, "artifacts"]

            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

        except Exception as e:
            logger.exception("Local task %s failed: %s", task_id, e)
            credit_transaction_id = payload.get("credit_transaction_id")
            if credit_transaction_id:
                try:
                    from src.services.credit_service import CreditService

                    task_record = await store.get_task_record(task_id)
                    if task_record is not None:
                        credit_service = CreditService(db)
                        await credit_service.refund_failed_task(
                            user_id=task_record.user_id,
                            original_transaction_id=str(credit_transaction_id),
                            reason="任务执行失败退款",
                            task_id=task_id,
                        )
                except Exception:
                    logger.exception("Failed to refund credits for task %s", task_id)
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))


def get_executor() -> TaskExecutor:
    """Factory: return CeleryExecutor or LocalExecutor based on settings."""
    if celery_settings.enabled:
        return CeleryExecutor()
    return LocalExecutor()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_executor.py -v`
Expected: PASS (4 tests)

**Step 5: Run ruff check**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run ruff check src/task/executor.py tests/task/test_executor.py`
Expected: All checks passed

**Step 6: Commit**

```bash
cd /home/cjz/AcademiaGPT-V2/backend
git add src/task/executor.py tests/task/test_executor.py
git commit -m "feat(task): add dual-mode executor (Celery + local asyncio fallback)"
```

---

### Task 3: Wire Executor into TaskService

**Files:**
- Modify: `backend/src/task/service.py:102-127` (submit_task Celery call)
- Create: `backend/tests/task/test_service_executor.py`

**Step 7: Write failing test for service integration**

```python
"""Tests for TaskService executor integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.task.service import TaskService


@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.count_active_tasks = AsyncMock(return_value=0)
    store.create_task_record = AsyncMock()
    return store


class TestSubmitTaskUsesExecutor:
    """TaskService.submit_task should delegate to get_executor()."""

    @pytest.mark.asyncio
    async def test_submit_calls_executor_not_celery_directly(self, mock_store):
        """submit_task should use executor abstraction, not celery_app.send_task."""
        service = TaskService(mock_store)

        mock_executor = AsyncMock()
        with (
            patch("src.task.service.get_executor", return_value=mock_executor),
            patch("src.task.service.is_valid_task_type", return_value=True),
            patch("src.task.service.get_task_config", return_value=MagicMock(queue="default")),
        ):
            task_id = await service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1"},
                priority=5,
            )

        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args
        assert call_kwargs.kwargs.get("task_id") or call_kwargs[0][0]  # task_id passed

    @pytest.mark.asyncio
    async def test_submit_marks_failed_on_executor_error(self, mock_store):
        """If executor.execute raises, task should be marked FAILED."""
        service = TaskService(mock_store)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = ConnectionError("broker down")

        with (
            patch("src.task.service.get_executor", return_value=mock_executor),
            patch("src.task.service.is_valid_task_type", return_value=True),
            patch("src.task.service.get_task_config", return_value=MagicMock(queue="default")),
        ):
            with pytest.raises(ConnectionError):
                await service.submit_task(
                    user_id="user-1",
                    task_type="workspace_feature",
                    payload={},
                )

        mock_store.update_task_record.assert_called_once()
```

**Step 8: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_service_executor.py -v`
Expected: FAIL — `submit_task` still calls `celery_app.send_task` directly

**Step 9: Modify service.py to use executor**

Replace lines 102-123 in `src/task/service.py`:

Old:
```python
        # Get task config
        config = get_task_config(task_type)

        # Submit to Celery
        try:
            celery_app.send_task(
                "src.task.tasks.execute_task",
                args=[task_id, task_type, payload],
                queue=config.queue if config else "default",
                priority=10 - priority,  # Celery uses inverse priority
                task_id=task_id,
            )
        except Exception as exc:
            logger.error(
                "Queue submission failed for task %s: %s", task_id, exc
            )
            await self._store.update_task_record(
                task_id,
                status=TaskStatus.FAILED.value,
                error=f"Queue submission failed: {exc}",
            )
            raise
```

New:
```python
        # Get task config
        config = get_task_config(task_type)

        # Submit via executor (Celery or local depending on config)
        from src.task.executor import get_executor

        try:
            executor = get_executor()
            await executor.execute(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                queue=config.queue if config else "default",
                priority=10 - priority,  # Celery uses inverse priority
            )
        except Exception as exc:
            logger.error(
                "Task submission failed for task %s: %s", task_id, exc
            )
            await self._store.update_task_record(
                task_id,
                status=TaskStatus.FAILED.value,
                error=f"Task submission failed: {exc}",
            )
            raise
```

Also remove the unused import `from src.task import celery_app` at line 8 (now only used in `cancel_task`). Actually check — `cancel_task` at line 222 uses `celery_app.control.revoke(task_id, terminate=True)`. Keep the import.

**Step 10: Run tests**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_service_executor.py tests/task/test_executor.py -v`
Expected: PASS (6 tests)

**Step 11: Run existing tests to verify no regression**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/ tests/services/test_release_gate.py tests/gateway/routers/test_features.py tests/application/handlers/test_feature_execution_handler.py -q`
Expected: All pass (existing tests mock submit_task or use TestClient overrides)

**Step 12: Commit**

```bash
cd /home/cjz/AcademiaGPT-V2/backend
git add src/task/service.py tests/task/test_service_executor.py
git commit -m "refactor(task): wire TaskService to executor abstraction"
```

---

### Task 4: Rate Limiting Activation — Failing Test

**Files:**
- Create: `backend/tests/gateway/test_rate_limiting.py`

**Step 13: Write failing test**

```python
"""Tests for rate limiting middleware activation."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_rate_limited_app(requests_per_minute: int = 3, window_seconds: int = 60) -> FastAPI:
    """Create a minimal app with rate limiting enabled."""
    from src.gateway.middleware.rate_limit import setup_rate_limiting

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # Use memory backend (no Redis needed for tests)
    with patch("src.gateway.middleware.rate_limit.settings") as mock_settings:
        mock_settings.RATE_LIMIT_REQUESTS = requests_per_minute
        mock_settings.RATE_LIMIT_WINDOW = window_seconds
        setup_rate_limiting(app, redis_client=None)

    return app


class TestRateLimiting:

    def test_requests_within_limit_succeed(self):
        app = _make_rate_limited_app(requests_per_minute=5)
        client = TestClient(app)
        for _ in range(5):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_requests_exceeding_limit_return_429(self):
        app = _make_rate_limited_app(requests_per_minute=3)
        client = TestClient(app)
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200

        resp = client.get("/test")
        assert resp.status_code == 429

    def test_health_endpoint_excluded_from_rate_limit(self):
        app = _make_rate_limited_app(requests_per_minute=1)
        client = TestClient(app)

        # Exhaust limit
        resp = client.get("/test")
        assert resp.status_code == 200

        # Health should still work
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        app = _make_rate_limited_app(requests_per_minute=10)
        client = TestClient(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
```

**Step 14: Run test to verify it passes (middleware already works)**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/gateway/test_rate_limiting.py -v`
Expected: PASS (the middleware code is complete, just not registered in main app)

**Step 15: Commit test**

```bash
cd /home/cjz/AcademiaGPT-V2/backend
git add tests/gateway/test_rate_limiting.py
git commit -m "test(gateway): add rate limiting middleware tests"
```

---

### Task 5: Register Rate Limiting in Gateway App

**Files:**
- Modify: `backend/src/gateway/middleware/__init__.py`
- Modify: `backend/src/gateway/app.py:84-97` (middleware section)

**Step 16: Update middleware __init__.py exports**

Add to `src/gateway/middleware/__init__.py`:

```python
"""Gateway middleware package."""

from src.gateway.middleware.correlation import (
    correlation_middleware,
    get_correlation_id,
)
from src.gateway.middleware.error_handler import register_error_handlers
from src.gateway.middleware.rate_limit import setup_rate_limiting

__all__ = [
    "correlation_middleware",
    "get_correlation_id",
    "register_error_handlers",
    "setup_rate_limiting",
]
```

**Step 17: Register in app.py**

Add after line 88 (correlation middleware) in `src/gateway/app.py`:

```python
# Rate limiting middleware
from src.academic.cache.redis_client import redis_client as _redis_client
from src.gateway.middleware import setup_rate_limiting

setup_rate_limiting(app, redis_client=_redis_client)
```

**Step 18: Run ruff check on modified files**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run ruff check src/gateway/middleware/__init__.py src/gateway/app.py`
Expected: All checks passed

**Step 19: Run full regression**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/ tests/services/test_release_gate.py tests/services/test_release_gate_service.py tests/gateway/routers/test_features.py tests/gateway/routers/test_dashboard.py tests/gateway/routers/test_dashboard_center.py tests/application/handlers/test_feature_execution_handler.py tests/gateway/test_rate_limiting.py -q`
Expected: All pass

**Step 20: Commit**

```bash
cd /home/cjz/AcademiaGPT-V2/backend
git add src/gateway/middleware/__init__.py src/gateway/app.py
git commit -m "feat(gateway): activate rate limiting middleware"
```

---

### Task 6: Sprint 1 Integration Verification

**Files:**
- Modify: `backend/src/quality/release_gate.py` (add executor test to gate)
- Modify: `backend/src/services/release_gate_service.py` (add executor test command)

**Step 21: Add executor test to release gate**

In `src/quality/release_gate.py`, add `"executor_dual_mode"` to `CORE_GATE_CHECKS`, `CHECK_DESCRIPTIONS`, and `CHECK_FIX_HINTS`.

In `src/services/release_gate_service.py`, add the corresponding `ReleaseGateCommand`:

```python
ReleaseGateCommand(
    check_id="executor_dual_mode",
    command=("uv", "run", "pytest", "tests/task/test_executor.py", "tests/task/test_service_executor.py", "-q"),
    cwd=self.backend_root,
),
```

**Step 22: Run release gate**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run python -m src.quality.release_gate_cli --output /tmp/sprint1-gate.json`
Expected: `status=passed`, `go_no_go=go`

**Step 23: Run ruff on all modified/new files**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run ruff check src/task/executor.py src/task/service.py src/gateway/app.py src/gateway/middleware/__init__.py src/quality/release_gate.py src/services/release_gate_service.py`
Expected: All checks passed

**Step 24: Final commit**

```bash
cd /home/cjz/AcademiaGPT-V2/backend
git add src/quality/release_gate.py src/services/release_gate_service.py
git commit -m "chore(gate): add executor_dual_mode to release gate checks"
```

---

### Sprint 1 Completion Checklist

- [ ] `src/task/executor.py` created with `CeleryExecutor`, `LocalExecutor`, `get_executor()`
- [ ] `src/task/service.py` uses `get_executor()` instead of `celery_app.send_task()`
- [ ] `src/gateway/app.py` registers rate limiting middleware
- [ ] `tests/task/test_executor.py` — 4 tests pass
- [ ] `tests/task/test_service_executor.py` — 2 tests pass
- [ ] `tests/gateway/test_rate_limiting.py` — 4 tests pass
- [ ] Release gate: `go_no_go=go`
- [ ] Ruff: all modified files pass
- [ ] Existing 122+ tests: no regressions
