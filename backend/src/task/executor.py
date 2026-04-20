"""Task executor abstraction (Celery-only)."""

from __future__ import annotations

from typing import Any, Protocol

from src.config.app_config import celery_settings

type JsonObject = dict[str, Any]


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


def get_executor(*, require_enabled: bool = True) -> TaskExecutor:
    """Factory: return CeleryExecutor.

    Args:
        require_enabled: When true, enforce CELERY_ENABLED=true before returning
            an executor. Callers can set this false to defer backend availability
            checks to dispatch time (useful for isolated unit tests).
    """
    global _CELERY_EXECUTOR
    if require_enabled and not celery_settings.enabled:
        raise RuntimeError("Task execution requires CELERY_ENABLED=true")
    if _CELERY_EXECUTOR is None:
        _CELERY_EXECUTOR = CeleryExecutor()
    return _CELERY_EXECUTOR


_CELERY_EXECUTOR: CeleryExecutor | None = None
