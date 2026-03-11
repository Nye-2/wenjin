"""Task storage abstraction for thesis generation tasks.

This module provides a storage abstraction layer that can be replaced
with Redis, database, or other persistent storage in production.
"""

import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ThesisTask:
    """Thesis generation task data."""
    task_id: str
    workspace_id: str
    paper_title: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    progress: float = 0.0
    current_phase: str = "init"
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Output data
    latex_content: str = ""
    bib_content: str = ""
    pdf_path: str = ""
    sections_completed: int = 0
    sections_total: int = 0

    # Error handling
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "paper_title": self.paper_title,
            "status": self.status,
            "progress": self.progress,
            "current_phase": self.current_phase,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "latex_content": self.latex_content,
            "bib_content": self.bib_content,
            "pdf_path": self.pdf_path,
            "sections_completed": self.sections_completed,
            "sections_total": self.sections_total,
            "error": self.error,
        }


class TaskStorage(ABC):
    """Abstract base class for task storage."""

    @abstractmethod
    def create_task(self, task: ThesisTask) -> None:
        """Create a new task."""
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[ThesisTask]:
        """Get task by ID."""
        pass

    @abstractmethod
    def update_task(self, task_id: str, updates: dict[str, Any]) -> Optional[ThesisTask]:
        """Update task with given fields."""
        pass

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """Delete task by ID."""
        pass

    @abstractmethod
    def list_tasks(self, workspace_id: Optional[str] = None) -> list[ThesisTask]:
        """List all tasks, optionally filtered by workspace."""
        pass


class InMemoryTaskStorage(TaskStorage):
    """Thread-safe in-memory task storage.

    Note: This is suitable for development and single-worker deployments.
    For production with multiple workers, use Redis or database-backed storage.
    """

    def __init__(self):
        self._tasks: dict[str, ThesisTask] = {}
        self._lock = threading.RLock()

    def create_task(self, task: ThesisTask) -> None:
        """Create a new task."""
        with self._lock:
            self._tasks[task.task_id] = task
            logger.debug(f"Created task {task.task_id}")

    def get_task(self, task_id: str) -> Optional[ThesisTask]:
        """Get task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def update_task(self, task_id: str, updates: dict[str, Any]) -> Optional[ThesisTask]:
        """Update task with given fields atomically."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            task.updated_at = datetime.now(UTC)
            logger.debug(f"Updated task {task_id}: {updates}")
            return task

    def delete_task(self, task_id: str) -> bool:
        """Delete task by ID."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.debug(f"Deleted task {task_id}")
                return True
            return False

    def list_tasks(self, workspace_id: Optional[str] = None) -> list[ThesisTask]:
        """List all tasks, optionally filtered by workspace."""
        with self._lock:
            tasks = list(self._tasks.values())
            if workspace_id:
                tasks = [t for t in tasks if t.workspace_id == workspace_id]
            return tasks

    def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """Remove tasks older than specified age.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of tasks removed
        """
        with self._lock:
            cutoff = datetime.now(UTC)
            to_remove = []

            for task_id, task in self._tasks.items():
                age_hours = (cutoff - task.created_at).total_seconds() / 3600
                if age_hours > max_age_hours and task.status in ("completed", "failed", "cancelled"):
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old tasks")

            return len(to_remove)


# Global storage instance
_storage: Optional[TaskStorage] = None


def get_storage() -> TaskStorage:
    """Get the global storage instance."""
    global _storage
    if _storage is None:
        _storage = InMemoryTaskStorage()
    return _storage


def set_storage(storage: TaskStorage) -> None:
    """Set the global storage instance (for testing or custom implementations)."""
    global _storage
    _storage = storage


def create_thesis_task(
    workspace_id: str,
    paper_title: str,
    **kwargs: Any,
) -> ThesisTask:
    """Create a new thesis generation task.

    Args:
        workspace_id: Workspace ID
        paper_title: Thesis title
        **kwargs: Additional task fields

    Returns:
        Created ThesisTask instance
    """
    task_id = str(uuid.uuid4())[:12]

    task = ThesisTask(
        task_id=task_id,
        workspace_id=workspace_id,
        paper_title=paper_title,
        **kwargs,
    )

    get_storage().create_task(task)
    logger.info(f"Created thesis task {task_id} for workspace {workspace_id}")

    return task


__all__ = [
    "ThesisTask",
    "TaskStorage",
    "InMemoryTaskStorage",
    "get_storage",
    "set_storage",
    "create_thesis_task",
]
