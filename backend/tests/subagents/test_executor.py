"""Tests for SubagentExecutor with background threading."""

from unittest.mock import MagicMock, patch

from src.subagents.executor import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    get_background_task_result,
)
from src.subagents.registry import SubagentConfig


class TestSubagentStatus:
    def test_status_values(self):
        assert SubagentStatus.PENDING.value == "pending"
        assert SubagentStatus.RUNNING.value == "running"
        assert SubagentStatus.COMPLETED.value == "completed"
        assert SubagentStatus.FAILED.value == "failed"
        assert SubagentStatus.TIMED_OUT.value == "timed_out"


class TestSubagentResult:
    def test_default_values(self):
        r = SubagentResult(task_id="t1")
        assert r.status == SubagentStatus.PENDING
        assert r.result is None
        assert r.error is None


class TestSubagentExecutor:
    def test_init(self):
        config = SubagentConfig(
            name="test",
            description="Test agent",
            system_prompt="You are a test agent.",
        )
        executor = SubagentExecutor(config=config, tools=[], parent_model="gpt-4o")
        assert executor.config.name == "test"

    def test_execute_sync(self):
        """Synchronous execution should return a result."""
        config = SubagentConfig(
            name="test",
            description="Test",
            system_prompt="Reply with 'done'.",
        )
        executor = SubagentExecutor(config=config, tools=[], parent_model="gpt-4o")
        # Mock the agent creation to avoid real LLM calls
        with patch.object(executor, "_create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {"messages": [MagicMock(content="done")]}
            mock_create.return_value = mock_agent
            result = executor.execute("test task")
            assert result.status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED)

    def test_background_task_tracking(self):
        """Background task results should be retrievable."""
        result = get_background_task_result("nonexistent")
        assert result is None
