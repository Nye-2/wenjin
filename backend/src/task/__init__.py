"""Async task system package."""

from src.task.celery_app import celery_app
from src.task.progress import ProgressTracker, get_progress_tracker
from src.task.registry import (
    TASK_REGISTRY,
    TaskQueue,
    TaskStatus,
    TaskTypeConfig,
    get_registered_task_types,
    get_task_config,
    is_valid_task_type,
)
from src.task.service import TaskService
from src.task.store import TaskStore


def start_worker(*args, **kwargs):
    """Lazily import and start the Celery worker entrypoint."""
    from src.task.worker import start_worker as _start_worker

    return _start_worker(*args, **kwargs)


def start_flower(*args, **kwargs):
    """Lazily import and start the Flower entrypoint."""
    from src.task.worker import start_flower as _start_flower

    return _start_flower(*args, **kwargs)

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
