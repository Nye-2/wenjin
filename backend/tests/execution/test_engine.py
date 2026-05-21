"""Tests for ExecutionEngineV2 (Task 2.6)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
    user_id: str = "user-001",
) -> SimpleNamespace:
    """Minimal stand-in for an ExecutionRecord ORM object."""
    return SimpleNamespace(
        id=execution_id,
        user_id=user_id,
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
    svc.append_execution_event = AsyncMock()
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
    """Happy path: runtime called, execution marked complete, run-history event recorded."""
    record = _make_execution_record()
    report = _make_task_report()

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
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

    # Run history was recorded as a canonical execution event.
    execution_svc.append_execution_event.assert_any_await(
        "exec-001",
        "execution.run_history",
        workspace_id="ws-001",
        node_id=None,
        payload_json={
            "capability_id": "test_cap",
            "title": "完成 Test Capability，共执行 1 个节点。",
            "summary": "完成 Test Capability，共执行 1 个节点。",
            "status": "completed",
            "duration_seconds": 2,
            "token_usage": {},
            "artifact_count": 0,
        },
    )


@pytest.mark.asyncio
async def test_engine_injects_lightweight_manuscript_context(monkeypatch: pytest.MonkeyPatch):
    """Runtime TaskBrief receives current Prism launch context when available."""
    record = _make_execution_record(user_id="user-1", workspace_id="ws-1")
    report = _make_task_report()
    execution_svc = _make_execution_service(record=record)
    execution_svc.db = object.__new__(AsyncSession)
    runtime = _make_runtime(report=report)
    prism_service = MagicMock()
    prism_service.get_launch_context_projection = AsyncMock(
        return_value={
            "main_file": "main.tex",
            "target_files": ["main.tex", "sections/intro.tex"],
            "pending_review_items": [
                {
                    "id": "review-1",
                    "target_file_path": "sections/intro.tex",
                }
            ],
        }
    )
    monkeypatch.setattr(
        "src.execution.engine.WorkspacePrismService",
        MagicMock(return_value=prism_service),
    )

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
    )

    await engine.run("exec-001")

    brief = runtime.run_session.call_args.kwargs["brief"]
    assert brief.manuscript_context["main_file"] == "main.tex"
    assert brief.manuscript_context["pending_review_items"][0]["id"] == "review-1"


# ---------------------------------------------------------------------------
# test_engine_marks_failed_on_runtime_exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_marks_failed_on_runtime_exception():
    """When the runtime raises, the engine marks execution failed and re-raises."""
    record = _make_execution_record()
    boom = RuntimeError("something went wrong in subagent")

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(raise_exc=boom)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
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

    # Run-history event is not recorded on failure.
    assert not any(
        call.args[1] == "execution.run_history"
        for call in execution_svc.append_execution_event.await_args_list
    )


@pytest.mark.asyncio
async def test_engine_persists_cancelled_status_from_runtime_report():
    """A cancelled runtime report must be written back as execution.status='cancelled'."""
    record = _make_execution_record()
    report = _make_task_report(status="cancelled")

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
    )

    await engine.run("exec-001")

    execution_svc.complete_execution.assert_called_once()
    complete_kwargs = execution_svc.complete_execution.call_args.kwargs
    assert complete_kwargs["status"] == "cancelled"
    assert "task_report" in complete_kwargs["result"]

    run_history_call = next(
        call
        for call in execution_svc.append_execution_event.await_args_list
        if call.args[1] == "execution.run_history"
    )
    assert run_history_call.kwargs["payload_json"]["status"] == "cancelled"


# ---------------------------------------------------------------------------
# test_engine_raises_for_missing_execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_raises_for_missing_execution():
    """When ExecutionService.get_by_id returns None, raise ValueError."""
    execution_svc = _make_execution_service(record=None)  # None = not found
    runtime = _make_runtime()

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
    )

    with pytest.raises(ValueError, match="exec-missing not found"):
        await engine.run("exec-missing")

    # Nothing else should have been called
    execution_svc.start_execution.assert_not_called()
    runtime.run_session.assert_not_called()
    execution_svc.append_execution_event.assert_not_called()
