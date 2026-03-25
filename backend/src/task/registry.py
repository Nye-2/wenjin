"""Task type registry for configuration and validation."""

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    """Task status values."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_statuses(cls) -> set["TaskStatus"]:
        """Return set of statuses that indicate task is done."""
        return {cls.SUCCESS, cls.FAILED, cls.CANCELLED}


class TaskQueue(StrEnum):
    """Available task queues."""
    DEFAULT = "default"
    LONG_RUNNING = "long_running"
    PRIORITY = "priority"


PAPER_EXTRACTION_TASK = "paper_extraction"
WORKSPACE_FEATURE_TASK = "workspace_feature"


@dataclass
class TaskTypeConfig:
    """Configuration for a task type."""
    queue: str = TaskQueue.DEFAULT
    timeout: int = 600  # seconds
    retry: int = 2
    retry_delay: int = 60  # seconds
    description: str = ""


# Task type registry
TASK_REGISTRY: dict[str, TaskTypeConfig] = {
    PAPER_EXTRACTION_TASK: TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=1,
        description="Paper extraction triggered from the papers API",
    ),
    WORKSPACE_FEATURE_TASK: TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=1,
        description="Generic workspace feature execution bridge",
    ),
}


def get_task_config(task_type: str) -> TaskTypeConfig | None:
    """Get configuration for a task type."""
    return TASK_REGISTRY.get(task_type)


def is_valid_task_type(task_type: str) -> bool:
    """Check if task type is registered."""
    return task_type in TASK_REGISTRY


def get_registered_task_types() -> list[str]:
    """Get all registered task types."""
    return list(TASK_REGISTRY.keys())
