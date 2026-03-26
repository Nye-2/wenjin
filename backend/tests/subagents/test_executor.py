"""Tests for SubagentExecutor async/sync execution paths."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.subagents.executor import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    get_background_task_result,
)
from src.subagents.registry import SubagentConfig


async def _async_iterator(items):
    for item in items:
        yield item


def _config() -> SubagentConfig:
    return SubagentConfig(
        name="test-agent",
        description="Test agent",
        system_prompt="You are a test agent.",
        max_turns=10,
    )


def _human(text: str) -> HumanMessage:
    return HumanMessage(content=text)


def _ai(content, msg_id: str | None = None) -> AIMessage:
    message = AIMessage(content=content)
    if msg_id:
        message.id = msg_id
    return message


class TestSubagentStatus:
    def test_status_values(self):
        assert SubagentStatus.PENDING.value == "pending"
        assert SubagentStatus.RUNNING.value == "running"
        assert SubagentStatus.COMPLETED.value == "completed"
        assert SubagentStatus.FAILED.value == "failed"
        assert SubagentStatus.TIMED_OUT.value == "timed_out"


class TestSubagentResult:
    def test_default_values(self):
        result = SubagentResult(task_id="t1")
        assert result.status == SubagentStatus.PENDING
        assert result.result is None
        assert result.error is None
        assert result.ai_messages == []


class TestSubagentExecutor:
    def test_init(self):
        executor = SubagentExecutor(config=_config(), tools=[], parent_model="gpt-4o")
        assert executor.config.name == "test-agent"

    @pytest.mark.asyncio
    async def test_aexecute_collects_final_result_and_messages(self):
        executor = SubagentExecutor(
            config=_config(),
            tools=[],
            thread_id="thread-1",
            workspace_id="ws-1",
            user_id="user-1",
            parent_model="gpt-4o",
        )
        msg1 = _ai("First response", "msg-1")
        msg2 = _ai("Final response", "msg-2")

        chunk1 = {"messages": [_human("Task"), msg1]}
        chunk2 = {"messages": [_human("Task"), msg1, msg2]}

        recorded: dict[str, object] = {}

        def _astream(*args, **kwargs):
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            return _async_iterator([chunk1, chunk2])

        mock_agent = MagicMock()
        mock_agent.astream = _astream

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor.aexecute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Final response"
        assert [message["id"] for message in result.ai_messages] == ["msg-1", "msg-2"]
        assert recorded["kwargs"]["config"] == {
            "recursion_limit": 10,
            "configurable": {
                "thread_id": "thread-1",
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "model_name": "gpt-4o",
            },
        }
        assert recorded["kwargs"]["stream_mode"] == "values"

    @pytest.mark.asyncio
    async def test_aexecute_handles_list_content(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        final_state = {
            "messages": [
                _human("Task"),
                _ai([{"text": "Part 1"}, {"text": "Part 2"}], "msg-1"),
            ]
        }
        mock_agent = MagicMock()
        mock_agent.astream = lambda *args, **kwargs: _async_iterator([final_state])

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor.aexecute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Part 1\nPart 2"

    @pytest.mark.asyncio
    async def test_aexecute_handles_agent_exception(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        mock_agent = MagicMock()
        async def _broken_astream(*args, **kwargs):
            raise Exception("Agent error")
            yield  # pragma: no cover

        mock_agent.astream = _broken_astream

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor.aexecute("Task")

        assert result.status == SubagentStatus.FAILED
        assert result.error == "Agent error"
        assert result.completed_at is not None

    def test_execute_runs_async_path_in_sync_context(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        final_state = {"messages": [_human("Task"), _ai("Sync result", "msg-1")]}
        mock_agent = MagicMock()
        mock_agent.astream = lambda *args, **kwargs: _async_iterator([final_state])

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor.execute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Sync result"

    def test_execute_works_from_thread_pool(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        final_state = {"messages": [_human("Task"), _ai("Thread result", "msg-1")]}

        def _run():
            mock_agent = MagicMock()
            mock_agent.astream = lambda *args, **kwargs: _async_iterator([final_state])
            with patch.object(executor, "_create_agent", return_value=mock_agent):
                return executor.execute("Task")

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_run).result(timeout=5)

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Thread result"

    def test_execute_reuses_result_holder(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        final_state = {"messages": [_human("Task"), _ai("Reusable result", "msg-1")]}
        result_holder = SubagentResult(
            task_id="existing-id",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        mock_agent = MagicMock()
        mock_agent.astream = lambda *args, **kwargs: _async_iterator([final_state])

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor.execute("Task", result_holder=result_holder)

        assert result is result_holder
        assert result.task_id == "existing-id"
        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Reusable result"

    def test_sync_execute_supports_async_tools(self):
        executor = SubagentExecutor(config=_config(), tools=[], thread_id="thread-1")
        async_tool_calls: list[str] = []

        async def _fake_async_tool():
            async_tool_calls.append("called")
            return "ok"

        async def _astream(*args, **kwargs):
            await _fake_async_tool()
            yield {"messages": [_human("Task"), _ai("Done", "msg-1")]}

        mock_agent = MagicMock()
        mock_agent.astream = _astream

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor.execute("Task")

        assert async_tool_calls == ["called"]
        assert result.status == SubagentStatus.COMPLETED

    def test_background_task_tracking(self):
        assert get_background_task_result("nonexistent") is None
