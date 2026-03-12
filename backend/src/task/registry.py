"""Task type registry for configuration and validation."""

from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
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


class TaskQueue(str, Enum):
    """Available task queues."""
    DEFAULT = "default"
    LONG_RUNNING = "long_running"
    PRIORITY = "priority"


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
    "deep_research": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=600,
        retry=2,
        description="Deep research: literature search, analysis, and summary",
    ),
    "thesis_generation": TaskTypeConfig(
        queue=TaskQueue.LONG_RUNNING,
        timeout=3600,
        retry=1,
        description="Thesis generation: full academic paper writing",
    ),
    "literature_search": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=2,
        description="Literature search: Semantic Scholar, arXiv search",
    ),
    "paper_processing": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=120,
        retry=1,
        description="Paper processing: PDF parsing, metadata extraction",
    ),
    "workspace_feature": TaskTypeConfig(
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
