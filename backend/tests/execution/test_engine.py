"""Tests for ExecutionEngineV2 (Task 2.6)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    token_usage: dict[str, int] | None = None,
) -> TaskReport:
    return TaskReport(
        execution_id=execution_id,
        capability_id=capability_id,
        status=status,
        duration_seconds=2,
        narrative="完成 Test Capability，共执行 1 个节点。",
        outputs=[],
        errors=[],
        token_usage=token_usage,
    )


def _make_execution_record(
    execution_id: str = "exec-001",
    workspace_id: str = "ws-001",
    feature_id: str | None = "test_cap",
    user_id: str = "user-001",
    workspace_type: str | None = None,
    credit_reservation_id: str | None = None,
) -> SimpleNamespace:
    """Minimal stand-in for an ExecutionRecord ORM object."""
    params: dict[str, Any] = {
        "brief": {
            "capability_id": "test_cap",
            "raw_message": "do the thing",
            "workspace_id": workspace_id,
            "brief": {"topic": "machine learning"},
            "decisions": {},
        }
    }
    if credit_reservation_id:
        params["billing"] = {"credit_reservation_id": credit_reservation_id}
    return SimpleNamespace(
        id=execution_id,
        user_id=user_id,
        workspace_id=workspace_id,
        workspace_type=workspace_type,
        feature_id=feature_id,
        params=params,
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
    assert call_kwargs["brief"].user_id == "user-001"

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
async def test_engine_settles_feature_token_billing_before_marking_complete():
    """Completed feature executions should settle measured token usage into credits."""
    record = _make_execution_record(user_id="user-001", workspace_id="ws-001")
    report = _make_task_report(token_usage={"input": 12000, "output": 3000})
    billing = SimpleNamespace(
        as_metadata=lambda: {
            "type": "feature_token_billing",
            "credits_charged": 2,
            "transaction_id": "credit-tx-1",
            "token_usage": {"input_tokens": 12000, "output_tokens": 3000, "total_tokens": 15000},
        }
    )
    credit_service = MagicMock()
    credit_service.consume_for_feature_usage = AsyncMock(return_value=billing)

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    with patch("src.services.credit_service.CreditService", return_value=credit_service):
        engine = ExecutionEngineV2(
            runtime=runtime,
            execution_service=execution_svc,
        )
        await engine.run("exec-001")

    credit_service.consume_for_feature_usage.assert_awaited_once_with(
        user_id="user-001",
        feature_id="test_cap",
        token_usage={"input": 12000, "output": 3000},
        workspace_id="ws-001",
        task_id="exec-001",
        metadata={
            "execution_id": "exec-001",
            "workspace_type": None,
            "source": "execution_engine",
        },
    )
    complete_result = execution_svc.complete_execution.await_args.kwargs["result"]
    assert complete_result["billing"]["transaction_id"] == "credit-tx-1"
    assert complete_result["token_usage"] == {
        "input_tokens": 12000,
        "output_tokens": 3000,
        "total_tokens": 15000,
    }


@pytest.mark.asyncio
async def test_engine_settles_feature_credit_reservation_when_present():
    record = _make_execution_record(
        user_id="user-001",
        workspace_id="ws-001",
        credit_reservation_id="reservation-1",
    )
    report = _make_task_report(token_usage={"input": 12000, "output": 3000})
    estimate = SimpleNamespace(
        as_metadata=lambda: {
            "type": "feature_token_billing",
            "credits_charged": 8,
            "token_usage": {"input_tokens": 12000, "output_tokens": 3000, "total_tokens": 15000},
            "charged": True,
        }
    )
    settled = SimpleNamespace(id="reservation-1", status="settled", transaction_id="credit-tx-1")
    tx = SimpleNamespace(id="credit-tx-1", balance_after=12)
    credit_service = MagicMock()
    credit_service.preview_feature_usage_charge = AsyncMock(return_value=estimate)
    credit_service.settle_feature_reservation = AsyncMock(return_value=(settled, tx))

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    with patch("src.services.credit_service.CreditService", return_value=credit_service):
        engine = ExecutionEngineV2(runtime=runtime, execution_service=execution_svc)
        await engine.run("exec-001")

    credit_service.preview_feature_usage_charge.assert_awaited_once()
    credit_service.settle_feature_reservation.assert_awaited_once_with(
        reservation_id="reservation-1",
        settled_credits=8,
        feature_id="test_cap",
        task_id="exec-001",
        metadata={
            "type": "feature_token_billing",
            "credits_charged": 8,
            "token_usage": {"input_tokens": 12000, "output_tokens": 3000, "total_tokens": 15000},
            "charged": True,
            "execution_id": "exec-001",
            "workspace_type": None,
            "source": "execution_engine",
        },
    )
    complete_result = execution_svc.complete_execution.await_args.kwargs["result"]
    assert complete_result["billing"]["credit_reservation_id"] == "reservation-1"
    assert complete_result["billing"]["transaction_id"] == "credit-tx-1"


@pytest.mark.asyncio
async def test_engine_skips_feature_billing_without_token_usage():
    """Executions without measured token usage should not write zero-charge billing noise."""
    record = _make_execution_record(user_id="user-001", workspace_id="ws-001")
    report = _make_task_report(token_usage=None)
    credit_service = MagicMock()
    credit_service.consume_for_feature_usage = AsyncMock()

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    with patch("src.services.credit_service.CreditService", return_value=credit_service):
        engine = ExecutionEngineV2(
            runtime=runtime,
            execution_service=execution_svc,
        )
        await engine.run("exec-001")

    credit_service.consume_for_feature_usage.assert_not_awaited()
    complete_result = execution_svc.complete_execution.await_args.kwargs["result"]
    assert "billing" not in complete_result
    assert "token_usage" not in complete_result


@pytest.mark.asyncio
async def test_engine_refunds_feature_billing_when_completion_persist_fails():
    """If billing succeeds but completion persistence fails, the ledger must be compensated."""
    record = _make_execution_record(user_id="user-001", workspace_id="ws-001")
    report = _make_task_report(token_usage={"input": 12000, "output": 3000})
    billing = SimpleNamespace(
        as_metadata=lambda: {
            "type": "feature_token_billing",
            "credits_charged": 2,
            "transaction_id": "credit-tx-1",
            "token_usage": {"input_tokens": 12000, "output_tokens": 3000, "total_tokens": 15000},
        }
    )
    credit_service = MagicMock()
    credit_service.consume_for_feature_usage = AsyncMock(return_value=billing)
    credit_service.refund_consumption = AsyncMock()

    execution_svc = _make_execution_service(record=record)
    execution_svc.complete_execution = AsyncMock(
        side_effect=[RuntimeError("execution store down"), None]
    )
    runtime = _make_runtime(report=report)

    with patch("src.services.credit_service.CreditService", return_value=credit_service):
        engine = ExecutionEngineV2(
            runtime=runtime,
            execution_service=execution_svc,
        )
        with pytest.raises(RuntimeError, match="execution store down"):
            await engine.run("exec-001")

    credit_service.refund_consumption.assert_awaited_once_with(
        user_id="user-001",
        original_transaction_id="credit-tx-1",
        reason="执行结果持久化失败退款",
        task_id="exec-001",
    )
    assert execution_svc.complete_execution.await_args_list[1].kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_engine_releases_feature_reservation_when_runtime_fails():
    record = _make_execution_record(
        user_id="user-001",
        workspace_id="ws-001",
        credit_reservation_id="reservation-1",
    )
    credit_service = MagicMock()
    credit_service.release_reservation = AsyncMock()

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(raise_exc=RuntimeError("runtime failed"))

    with patch("src.services.credit_service.CreditService", return_value=credit_service):
        engine = ExecutionEngineV2(runtime=runtime, execution_service=execution_svc)
        with pytest.raises(RuntimeError, match="runtime failed"):
            await engine.run("exec-001")

    credit_service.release_reservation.assert_awaited_once_with(
        "reservation-1",
        reason="执行失败释放预留积分",
    )


@pytest.mark.asyncio
async def test_engine_injects_lightweight_manuscript_context(monkeypatch: pytest.MonkeyPatch):
    """Runtime TaskBrief receives current Prism launch context when available."""
    class _ClientContext:
        def __init__(self, client: object) -> None:
            self.client = client

        async def __aenter__(self) -> object:
            return self.client

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    fake_client = SimpleNamespace(
        get_catalog_capability=AsyncMock(
            return_value=SimpleNamespace(
                definition_json={"mission": {"primary_surface": "prism"}},
                graph_template={},
            )
        ),
    )
    monkeypatch.setattr(
        "src.execution.engine.dataservice_client",
        lambda: _ClientContext(fake_client),
    )

    record = _make_execution_record(
        user_id="user-1",
        workspace_id="ws-1",
        feature_id="research_question_to_paper",
        workspace_type="sci",
    )
    record.params["brief"]["capability_id"] = "research_question_to_paper"
    report = _make_task_report()
    execution_svc = _make_execution_service(record=record)
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


@pytest.mark.asyncio
async def test_engine_ensures_prism_surface_for_prism_capability(
    monkeypatch: pytest.MonkeyPatch,
):
    """Prism-primary capabilities should not silently run without Prism context."""

    class _ClientContext:
        def __init__(self, client: object) -> None:
            self.client = client

        async def __aenter__(self) -> object:
            return self.client

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    fake_client = SimpleNamespace(
        get_catalog_capability=AsyncMock(
            return_value=SimpleNamespace(
                definition_json={"mission": {"primary_surface": "prism"}},
                graph_template={},
            )
        ),
        get_workspace=AsyncMock(return_value=SimpleNamespace(name="SCI Workspace")),
    )
    monkeypatch.setattr(
        "src.execution.engine.dataservice_client",
        lambda: _ClientContext(fake_client),
    )

    record = _make_execution_record(
        user_id="user-1",
        workspace_id="ws-1",
        feature_id="research_question_to_paper",
        workspace_type="sci",
    )
    record.params["brief"]["capability_id"] = "research_question_to_paper"
    report = _make_task_report(capability_id="research_question_to_paper")
    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(report=report)

    prism_service = MagicMock()
    prism_service.get_launch_context_projection = AsyncMock(
        side_effect=[
            ValueError("Workspace Prism not found"),
            {
                "latex_project_id": "latex-1",
                "main_file": "main.tex",
                "target_files": ["main.tex"],
            },
        ]
    )
    prism_service.ensure_primary_project = AsyncMock()
    monkeypatch.setattr(
        "src.execution.engine.WorkspacePrismService",
        MagicMock(return_value=prism_service),
    )

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
    )

    await engine.run("exec-001")

    prism_service.ensure_primary_project.assert_awaited_once_with(
        "ws-1",
        user_id="user-1",
        project_name="SCI Workspace",
    )
    brief = runtime.run_session.call_args.kwargs["brief"]
    assert brief.manuscript_context["latex_project_id"] == "latex-1"
    assert brief.manuscript_context["main_file"] == "main.tex"


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
async def test_engine_marks_failed_when_reservation_release_also_fails():
    """Cleanup failures must not leave the execution stuck in running."""
    record = _make_execution_record(credit_reservation_id="reservation-1")
    boom = RuntimeError("primary execution failure")

    execution_svc = _make_execution_service(record=record)
    runtime = _make_runtime(raise_exc=boom)

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
    )
    engine._release_feature_reservation = AsyncMock(side_effect=RuntimeError("release failed"))

    with pytest.raises(RuntimeError, match="primary execution failure"):
        await engine.run("exec-001")

    engine._release_feature_reservation.assert_awaited_once()
    execution_svc.complete_execution.assert_called_once()
    fail_kwargs = execution_svc.complete_execution.call_args.kwargs
    assert fail_kwargs["status"] == "failed"
    assert "primary execution failure" in fail_kwargs["error"]


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
