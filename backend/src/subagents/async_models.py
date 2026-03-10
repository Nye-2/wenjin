"""Async data models for Phase 2 subagent system."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SubagentTaskStatus(str, Enum):
    """Status of a subagent task (async version)."""

    PENDING = "pending"       # Waiting for execution slot
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Execution failed
    CANCELLED = "cancelled"   # Cancelled by user
    TIMEOUT = "timeout"       # Exceeded time limit


@dataclass
class SubagentTaskDef:
    """Definition of a subagent task (async version)."""

    task_id: str
    thread_id: str
    prompt: str
    graph_template: str = "default"
    max_turns: int = 10
    timeout: int = 900  # 15 minutes
    created_at: datetime = field(default_factory=datetime.now)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "prompt": self.prompt,
            "graph_template": self.graph_template,
            "max_turns": self.max_turns,
            "timeout": self.timeout,
            "created_at": self.created_at.isoformat() if self.created_at else None
            "tools": self.tools,
            "metadata": self.metadata
        }


@dataclass
class SubagentTaskEvent:
    """Event emitted during subagent execution (async version)."""

    event_type: str  # task_started, turn_complete, task_completed, task_failed, task_cancelled
    task_id: str
    thread_id: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Convert event to SSE format string."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.to_dict())}\n\n    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
