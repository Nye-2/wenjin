"""Tests for subagent data models."""

import json
from datetime import UTC, datetime

import pytest

from src.subagents.models import SubagentStatus, SubagentTask, SubagentEvent, SubagentResult


class TestSubagentStatus:
    """Tests for SubagentStatus enum."""

    def test_status_values(self):
        """Test that all required status values exist."""
        assert SubagentStatus.PENDING.value == "pending"
        assert SubagentStatus.RUNNING.value == "running"
        assert SubagentStatus.COMPLETED.value == "completed"
        assert SubagentStatus.FAILED.value == "failed"
        assert SubagentStatus.CANCELLED.value == "cancelled"
        assert SubagentStatus.TIMED_OUT.value == "timed_out"

    def test_status_is_string_enum(self):
        """Test that SubagentStatus is a string enum."""
        assert isinstance(SubagentStatus.PENDING, str)
        assert SubagentStatus.PENDING == "pending"


class TestSubagentTask:
    """Tests for SubagentTask dataclass."""

    def test_task_creation_minimal(self):
        """Test creating a task with minimal required fields."""
        now = datetime.now(UTC)
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test prompt",
            created_at=now,
        )
        assert task.task_id == "task-123"
        assert task.thread_id == "thread-456"
        assert task.prompt == "Test prompt"
        assert task.graph_template == "default"
        assert task.max_turns == 10
        assert task.timeout == 900
        assert task.created_at == now
        assert task.tools == []
        assert task.metadata == {}

    def test_task_creation_full(self):
        """Test creating a task with all fields."""
        now = datetime.now(UTC)
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test prompt",
            graph_template="custom",
            max_turns=20,
            timeout=600,
            created_at=now,
            tools=["bash", "read_file"],
            metadata={"key": "value"},
        )
        assert task.task_id == "task-123"
        assert task.thread_id == "thread-456"
        assert task.prompt == "Test prompt"
        assert task.graph_template == "custom"
        assert task.max_turns == 20
        assert task.timeout == 600
        assert task.created_at == now
        assert task.tools == ["bash", "read_file"]
        assert task.metadata == {"key": "value"}

    def test_task_to_dict(self):
        """Test task serialization to dictionary."""
        now = datetime.now(UTC)
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test prompt",
            created_at=now,
        )
        result = task.to_dict()
        assert result["task_id"] == "task-123"
        assert result["thread_id"] == "thread-456"
        assert result["prompt"] == "Test prompt"
        assert result["graph_template"] == "default"
        assert result["max_turns"] == 10
        assert result["timeout"] == 900
        assert "created_at" in result
        assert result["tools"] == []
        assert result["metadata"] == {}

    def test_task_to_dict_json_serializable(self):
        """Test that to_dict output is JSON serializable."""
        now = datetime.now(UTC)
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test prompt",
            created_at=now,
        )
        result = task.to_dict()
        # Should not raise
        json.dumps(result)


class TestSubagentEvent:
    """Tests for SubagentEvent dataclass."""

    def test_event_creation(self):
        """Test creating an event."""
        now = datetime.now(UTC)
        event = SubagentEvent(
            event_type="progress",
            task_id="task-123",
            thread_id="thread-456",
            data={"message": "Working..."},
            timestamp=now,
        )
        assert event.event_type == "progress"
        assert event.task_id == "task-123"
        assert event.thread_id == "thread-456"
        assert event.data == {"message": "Working..."}
        assert event.timestamp == now

    def test_event_to_sse(self):
        """Test SSE format conversion."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        event = SubagentEvent(
            event_type="completed",
            task_id="task-123",
            thread_id="thread-456",
            data={"output": "Done!"},
            timestamp=now,
        )
        sse = event.to_sse()
        assert "event: completed" in sse
        assert '"task_id": "task-123"' in sse
        assert '"output": "Done!"' in sse
        assert sse.endswith("\n\n")

    def test_event_to_sse_format(self):
        """Test that to_sse returns correct SSE format."""
        now = datetime.now(UTC)
        event = SubagentEvent(
            event_type="started",
            task_id="task-123",
            thread_id="thread-456",
            data={},
            timestamp=now,
        )
        sse = event.to_sse()
        lines = sse.strip().split("\n")
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")

    def test_event_to_dict(self):
        """Test event serialization to dictionary."""
        now = datetime.now(UTC)
        event = SubagentEvent(
            event_type="progress",
            task_id="task-123",
            thread_id="thread-456",
            data={"percent": 50},
            timestamp=now,
        )
        result = event.to_dict()
        assert result["event_type"] == "progress"
        assert result["task_id"] == "task-123"
        assert result["thread_id"] == "thread-456"
        assert result["data"] == {"percent": 50}
        assert "timestamp" in result

    def test_event_to_dict_json_serializable(self):
        """Test that to_dict output is JSON serializable."""
        now = datetime.now(UTC)
        event = SubagentEvent(
            event_type="progress",
            task_id="task-123",
            thread_id="thread-456",
            data={"percent": 50},
            timestamp=now,
        )
        result = event.to_dict()
        # Should not raise
        json.dumps(result)


class TestSubagentResult:
    """Tests for SubagentResult dataclass."""

    def test_result_creation_success(self):
        """Test creating a successful result."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.COMPLETED,
            output="Task completed successfully",
            error=None,
            turns_used=5,
            duration_seconds=10.5,
            metadata={},
        )
        assert result.task_id == "task-123"
        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "Task completed successfully"
        assert result.error is None
        assert result.turns_used == 5
        assert result.duration_seconds == 10.5
        assert result.metadata == {}

    def test_result_creation_failure(self):
        """Test creating a failed result."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.FAILED,
            output=None,
            error="Something went wrong",
            turns_used=3,
            duration_seconds=5.0,
            metadata={"error_type": "RuntimeError"},
        )
        assert result.task_id == "task-123"
        assert result.status == SubagentStatus.FAILED
        assert result.output is None
        assert result.error == "Something went wrong"
        assert result.turns_used == 3
        assert result.duration_seconds == 5.0
        assert result.metadata == {"error_type": "RuntimeError"}

    def test_result_defaults(self):
        """Test result default values."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.COMPLETED,
            output="Done",
            error=None,
        )
        assert result.turns_used == 0
        assert result.duration_seconds == 0.0
        assert result.metadata == {}

    def test_result_to_dict(self):
        """Test result serialization to dictionary."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.COMPLETED,
            output="Done",
            error=None,
            turns_used=5,
            duration_seconds=10.5,
            metadata={"key": "value"},
        )
        d = result.to_dict()
        assert d["task_id"] == "task-123"
        assert d["status"] == "completed"
        assert d["output"] == "Done"
        assert d["error"] is None
        assert d["turns_used"] == 5
        assert d["duration_seconds"] == 10.5
        assert d["metadata"] == {"key": "value"}

    def test_result_to_dict_json_serializable(self):
        """Test that to_dict output is JSON serializable."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.COMPLETED,
            output="Done",
            error=None,
        )
        d = result.to_dict()
        # Should not raise
        json.dumps(d)

    def test_result_all_statuses(self):
        """Test result creation with all status types."""
        for status in SubagentStatus:
            result = SubagentResult(
                task_id="task-123",
                status=status,
                output=None if status != SubagentStatus.COMPLETED else "Done",
                error=None if status == SubagentStatus.COMPLETED else "Error",
            )
            assert result.status == status
            d = result.to_dict()
            assert d["status"] == status.value
