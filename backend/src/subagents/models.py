"""Data models for subagent system."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SubagentStatus(str, Enum):
    """Status of a subagent task."""
    PENDING = "pending"       # Waiting for execution slot
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Execution failed
    CANCELLED = "cancelled"   # Cancelled by user
    TIMEOUT = "timeout"       # Exceeded time limit


@dataclass
class SubagentTask:
    """Represents a subagent task to be executed."""
    task_id: str
    thread_id: str
    prompt: str
    created_at: datetime
    graph_template: str = "default"
    max_turns: int = 10
    timeout: int = 900
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "prompt": self.prompt,
            "graph_template": self.graph_template,
            "max_turns": self.max_turns,
            "timeout": self.timeout,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tools": self.tools,
            "metadata": self.metadata,
        }


@dataclass
class SubagentEvent:
    """Represents an event from subagent execution for SSE streaming."""
    event_type: str
    task_id: str
    thread_id: str
    data: dict[str, Any]
    timestamp: datetime

    def to_sse(self) -> str:
        """Convert event to SSE format string."""
        payload = json.dumps(self.to_dict())
        return f"event: {self.event_type}\ndata: {payload}\n\n"

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class SubagentResult:
    """Represents the final result of a subagent task."""
    task_id: str
    status: SubagentStatus
    output: Optional[str]
    error: Optional[str]
    turns_used: int = 0
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value if isinstance(self.status, SubagentStatus) else self.status,
            "output": self.output,
            "error": self.error,
            "turns_used": self.turns_used,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }
