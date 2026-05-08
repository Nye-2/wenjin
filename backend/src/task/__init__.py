"""Async task system package."""

from typing import Any

from src.task.celery_app import celery_app
from src.task.registry import (
    TASK_REGISTRY,
    TaskQueue,
    TaskStatus,
    TaskTypeConfig,
    get_registered_task_types,
    get_task_config,
    is_valid_task_type,
)


def start_worker(*args: Any, **kwargs: Any) -> Any:
    """Lazily import and start the Celery worker entrypoint."""
    from src.task.worker import start_worker as _start_worker

    return _start_worker(*args, **kwargs)


def start_flower(*args: Any, **kwargs: Any) -> Any:
    """Lazily import and start the Flower entrypoint."""
    from src.task.worker import start_flower as _start_flower

    return _start_flower(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "get_progress_tracker":
        from src.task.progress import get_progress_tracker

        return get_progress_tracker
    if name == "ProgressTracker":
        from src.task.progress import ProgressTracker

        return ProgressTracker
    if name == "TaskService":
        from src.task.service import TaskService

        return TaskService
    if name == "TaskStore":
        from src.task.store import TaskStore

        return TaskStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Celery
    "celery_app",
    # Service
    "TaskService",
    "TaskStore",
    # Progress
    "ProgressTracker",
    "get_progress_tracker",
    # Registry
    "TASK_REGISTRY",
    "TaskQueue",
    "TaskStatus",
    "TaskTypeConfig",
    "get_task_config",
    "is_valid_task_type",
    "get_registered_task_types",
    # Worker
    "start_worker",
    "start_flower",
]
