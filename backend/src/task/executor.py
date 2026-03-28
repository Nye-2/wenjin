"""Task executor abstraction — dual-mode (Celery / local asyncio)."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, Protocol, TypeAlias

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, Any]


class CeleryAppProtocol(Protocol):
    """Minimal Celery app surface used by the executor."""

    def send_task(
        self,
        name: str,
        *,
        args: list[object],
        queue: str,
        priority: int,
        task_id: str,
    ) -> object: ...


class TaskExecutor(Protocol):
    """Protocol for task execution backends."""

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: JsonObject,
        queue: str,
        *,
        priority: int = 5,
    ) -> None: ...


class CeleryExecutor:
    """Submit tasks to Celery broker queue."""

    def __init__(self, celery_app: CeleryAppProtocol | None = None) -> None:
        if celery_app is None:
            from src.task import celery_app as _app
            celery_app = _app
        self._celery_app = celery_app

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: JsonObject,
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
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def execute(
        self,
        task_id: str,
        task_type: str,
        payload: JsonObject,
        queue: str,
        *,
        priority: int = 5,
    ) -> None:
        task = asyncio.create_task(self._guarded_run(task_id, task_type, payload))
        self._tasks[task_id] = task

        def _cleanup(_done: asyncio.Task[None]) -> None:
            self._tasks.pop(task_id, None)

        task.add_done_callback(_cleanup)

    async def _guarded_run(
        self,
        task_id: str,
        task_type: str,
        payload: JsonObject,
    ) -> None:
        async with self._semaphore:
            await _run_task_locally(task_id, task_type, payload)

    def cancel(self, task_id: str) -> bool:
        """Cancel a local in-process task by id."""
        task = self._tasks.get(task_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True


async def _run_task_locally(
    task_id: str,
    task_type: str,
    payload: JsonObject,
) -> None:
    """Run a task in-process via the same shared execution flow as Celery."""
    from src.task.tasks.base import _execute_task_async

    local_task = SimpleNamespace(request=SimpleNamespace(hostname="local-executor"))
    try:
        await _execute_task_async(local_task, task_id, task_type, payload)
    except Exception:
        # The shared runner already persisted failure state and emitted best-effort
        # terminal events. Local executor keeps background-task semantics and does
        # not re-raise into the caller.
        logger.debug("Local task %s finished with handled failure state", task_id)


def get_executor() -> TaskExecutor:
    """Factory: return CeleryExecutor or LocalExecutor based on settings."""
    global _CELERY_EXECUTOR, _LOCAL_EXECUTOR

    if celery_settings.enabled:
        if _CELERY_EXECUTOR is None:
            _CELERY_EXECUTOR = CeleryExecutor()
        return _CELERY_EXECUTOR

    if _LOCAL_EXECUTOR is None:
        _LOCAL_EXECUTOR = LocalExecutor()
    return _LOCAL_EXECUTOR


def cancel_local_task(task_id: str) -> bool:
    """Cancel task in local executor mode."""
    if _LOCAL_EXECUTOR is None:
        return False
    return _LOCAL_EXECUTOR.cancel(task_id)


_CELERY_EXECUTOR: CeleryExecutor | None = None
_LOCAL_EXECUTOR: LocalExecutor | None = None
