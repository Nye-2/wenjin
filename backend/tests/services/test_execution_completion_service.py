"""Tests for ExecutionCompletionService (Task 2.10)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.contracts.task_report import TaskReport
from src.services.execution_completion_service import ExecutionCompletionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXECUTION_ID = "exec-completion-1"
WORKSPACE_ID = "ws-completion-1"
THREAD_ID = "thread-completion-1"


def _make_report() -> TaskReport:
    return TaskReport(
        execution_id=EXECUTION_ID,
        capability_id="cap-1",
        status="completed",
        duration_seconds=5,
        narrative="Completed successfully.",
    )


def _make_execution(workspace_id: str = WORKSPACE_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=EXECUTION_ID,
        workspace_id=workspace_id,
        user_id="user-1",
    )


def _make_workspace(thread_id: str | None = THREAD_ID) -> SimpleNamespace:
    return SimpleNamespace(id=WORKSPACE_ID, thread_id=thread_id)


def _make_thread(thread_id: str = THREAD_ID) -> MagicMock:
    thread = MagicMock()
    thread.id = thread_id
    return thread


def _make_service(
    *,
    execution=None,
    workspace=None,
    thread=None,
    add_message_return=None,
    add_message_side_effect=None,
) -> ExecutionCompletionService:
    execution_svc = MagicMock()
    execution_svc.get_by_id = AsyncMock(return_value=execution)

    workspace_svc = MagicMock()
    workspace_svc.get_by_id = AsyncMock(return_value=workspace)

    thread_svc = MagicMock()
    thread_svc.get_by_id = AsyncMock(return_value=thread)
    if add_message_side_effect is not None:
        thread_svc.add_message = AsyncMock(side_effect=add_message_side_effect)
    else:
        thread_svc.add_message = AsyncMock(
            return_value=add_message_return or {"timestamp": "2026-05-09T00:00:00", "role": "system"}
        )

    return ExecutionCompletionService(
        thread_service=thread_svc,
        execution_service=execution_svc,
        workspace_service=workspace_svc,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_appends_system_message():
    """Happy path: deliver() calls thread.add_message with correct payload."""
    execution = _make_execution()
    workspace = _make_workspace(thread_id=THREAD_ID)
    thread = _make_thread(THREAD_ID)
    report = _make_report()

    svc = _make_service(execution=execution, workspace=workspace, thread=thread)

    result = await svc.deliver(EXECUTION_ID, report)

    assert result is not None
    svc.threads.add_message.assert_called_once()
    call_kwargs = svc.threads.add_message.call_args

    # Verify role and content
    assert call_kwargs.kwargs.get("role") == "system" or call_kwargs.args[1:2] == ("system",)
    content_arg = call_kwargs.kwargs.get("content", "")
    payload = json.loads(content_arg)
    assert payload["kind"] == "execution_completed"
    assert payload["execution_id"] == EXECUTION_ID
    assert "task_report" in payload
    assert payload["task_report"]["status"] == "completed"


@pytest.mark.asyncio
async def test_deliver_returns_none_for_missing_execution():
    """Execution not found → returns None, no thread call."""
    report = _make_report()
    svc = _make_service(execution=None)

    result = await svc.deliver(EXECUTION_ID, report)

    assert result is None
    svc.threads.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_returns_none_for_missing_thread():
    """Workspace has no thread_id → returns None, no thread call."""
    execution = _make_execution()
    workspace = _make_workspace(thread_id=None)
    report = _make_report()

    svc = _make_service(execution=execution, workspace=workspace)

    result = await svc.deliver(EXECUTION_ID, report)

    assert result is None
    svc.threads.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_swallows_thread_failure():
    """thread.add_message raises → returns None (logged), does not propagate."""
    execution = _make_execution()
    workspace = _make_workspace(thread_id=THREAD_ID)
    thread = _make_thread(THREAD_ID)
    report = _make_report()

    svc = _make_service(
        execution=execution,
        workspace=workspace,
        thread=thread,
        add_message_side_effect=RuntimeError("DB connection lost"),
    )

    result = await svc.deliver(EXECUTION_ID, report)

    # Must not raise; returns None
    assert result is None


@pytest.mark.asyncio
async def test_deliver_returns_none_when_workspace_service_is_none():
    """When workspace_service is not provided, thread_id cannot be resolved → None."""
    execution = _make_execution()
    report = _make_report()

    execution_svc = MagicMock()
    execution_svc.get_by_id = AsyncMock(return_value=execution)
    thread_svc = MagicMock()
    thread_svc.add_message = AsyncMock()

    svc = ExecutionCompletionService(
        thread_service=thread_svc,
        execution_service=execution_svc,
        workspace_service=None,
    )

    result = await svc.deliver(EXECUTION_ID, report)

    assert result is None
    thread_svc.add_message.assert_not_called()
