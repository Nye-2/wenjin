"""Tests for ExecutionEngineV2 (Task 2.6)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.agents.contracts.task_report import TaskReport
from src.execution.engine import ExecutionEngineV2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_report(
    execution_id: str = "exec-001",
    capability_id: str = "test_cap",
    status: str = "completed",
) -> TaskReport:
    return TaskReport(
        execution_id=execution_id,
        capability_id=capability_id,
        status=status,
        duration_seconds=2,
        narrative="完成 Test Capability，共执行 1 个节点。",
        outputs=[],
        errors=[],
        token_usage=None,
    )


def _make_execution_record(
    execution_id: str = "exec-001",
    workspace_id: str = "ws-001",
    feature_id: str | None = "test_cap",
) -> SimpleNamespace:
    """Minimal stand-in for an ExecutionRecord ORM object."""
    return SimpleNamespace(
        id=execution_id,
        workspace_id=workspace_id,
        feature_id=feature_id,
        params={
            "brief": {
                "capability_id": "test_cap",
                "raw_message": "do the thing",
                "workspace_id": workspace_id,
                "brief": {"topic": "machine learning"},
                "decisions": {},
            }
        },
    )


def _make_execution_service(record=None) -> MagicMock:
    svc = MagicMock()
    svc.get_by_id = AsyncMock(return_value=record)
    svc.start_execution = AsyncMock()
    svc.complete_execution = AsyncMock()
    return svc


def _make_run_history_service() -> MagicMock:
    svc = MagicMock()
    svc.record = AsyncMock()
    return svc


def _make_runtime(report: TaskReport | None = None, *, raise_exc: Exception | None = None) -> MagicMock:
    runtime = MagicMock()
    if raise_exc is not None:
        runtime.run_session = AsyncMock(side_effect=raise_exc)
    else:
        runtime.run_session = AsyncMock(return_value=report or _make_task_report())
    return runtime


# ---------------------------------------------------------------------------
# test_engine_runs_lead_agent_and_marks_complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_runs_lead_agent_and_marks_complete():
    """Happy path: runtime called, execution marked complete, run_history recorded."""
    record = _make_execution_record()
    report = _make_task_report()

    execution_svc = _make_execution_service(record=record)
    history_svc = _make_run_history_service()
    runtime = _make_runtime(report=report)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
        run_history_service=history_svc,
    )

    await engine.run("exec-001")

    # Runtime was invoked
    runtime.run_session.assert_called_once()
    call_kwargs = runtime.run_session.call_args.kwargs
    assert call_kwargs["execution_id"] == "exec-001"

    # Execution was marked running
    execution_svc.start_execution.assert_called_once_with("exec-001")

    # Execution was marked complete
    execution_svc.complete_execution.assert_called_once()
    complete_kwargs = execution_svc.complete_execution.call_args.kwargs
    assert complete_kwargs["status"] == "completed"
    assert "task_report" in complete_kwargs["result"]

    # Run history was recorded
    history_svc.record.assert_called_once()
    record_args = history_svc.record.call_args
    # Positional args: workspace_id, execution_id, capability_id, title, summary, status, duration_seconds
    positional = record_args.args
    assert positional[0] == "ws-001"       # workspace_id
    assert positional[1] == "exec-001"     # execution_id
    assert positional[2] == "test_cap"     # capability_id (from feature_id)
    assert positional[5] == "completed"    # status
    assert positional[6] == 2              # duration_seconds


# ---------------------------------------------------------------------------
# test_engine_marks_failed_on_runtime_exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_marks_failed_on_runtime_exception():
    """When the runtime raises, the engine marks execution failed and re-raises."""
    record = _make_execution_record()
    boom = RuntimeError("something went wrong in subagent")

    execution_svc = _make_execution_service(record=record)
    history_svc = _make_run_history_service()
    runtime = _make_runtime(raise_exc=boom)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
        run_history_service=history_svc,
    )

    with pytest.raises(RuntimeError, match="something went wrong"):
        await engine.run("exec-001")

    # Still marked running before failure
    execution_svc.start_execution.assert_called_once_with("exec-001")

    # Marked failed
    execution_svc.complete_execution.assert_called_once()
    fail_kwargs = execution_svc.complete_execution.call_args.kwargs
    assert fail_kwargs["status"] == "failed"
    assert "something went wrong" in fail_kwargs["error"]

    # Run history NOT recorded on failure
    history_svc.record.assert_not_called()


# ---------------------------------------------------------------------------
# test_engine_raises_for_missing_execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_raises_for_missing_execution():
    """When ExecutionService.get_by_id returns None, raise ValueError."""
    execution_svc = _make_execution_service(record=None)  # None = not found
    history_svc = _make_run_history_service()
    runtime = _make_runtime()

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
        run_history_service=history_svc,
    )

    with pytest.raises(ValueError, match="exec-missing not found"):
        await engine.run("exec-missing")

    # Nothing else should have been called
    execution_svc.start_execution.assert_not_called()
    runtime.run_session.assert_not_called()
    history_svc.record.assert_not_called()
