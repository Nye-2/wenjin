"""Tests for cancel_execution in ExecutionService (Task 2.11)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.agents.contracts.task_report import TaskReport
from src.execution.engine import ExecutionEngineV2
from src.services.execution_service import ExecutionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXECUTION_ID = "exec-cancel-1"


def _make_record(status: str) -> SimpleNamespace:
    ns = SimpleNamespace(
        id=EXECUTION_ID,
        status=status,
        user_id="user-1",
        workspace_id="ws-1",
        updated_at=None,
        completed_at=None,
    )
    return ns


def _make_db_with_record(record) -> MagicMock:
    """Return a mock AsyncSession that returns record from get_by_id's query."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_service(record, *, redis=None, publish_event=None):
    """Build an ExecutionService whose get_by_id is patched to return record."""
    db = _make_db_with_record(record)
    svc = ExecutionService(db, redis=redis, publish_event=publish_event)
    svc.get_by_id = AsyncMock(return_value=record)
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_sets_status_to_cancelling():
    """cancel_execution on a running execution → status becomes 'cancelling'."""
    record = _make_record("running")
    svc = _make_service(record)

    result = await svc.cancel_execution(EXECUTION_ID)

    assert result is record
    assert record.status == "cancelling"
    svc.db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_sets_redis_abort_signal():
    """cancel_execution writes the Redis abort key."""
    record = _make_record("running")

    redis_mock = MagicMock()
    redis_mock.set = AsyncMock()

    svc = _make_service(record, redis=redis_mock)
    await svc.cancel_execution(EXECUTION_ID)

    redis_mock.set.assert_called_once_with(
        f"abort:exec:{EXECUTION_ID}", "1", ex=300
    )


@pytest.mark.asyncio
async def test_cancel_publishes_status_event():
    """cancel_execution calls publish_event with 'execution.status' and 'cancelling'."""
    record = _make_record("running")
    publish_event = AsyncMock()

    svc = _make_service(record, publish_event=publish_event)
    await svc.cancel_execution(EXECUTION_ID)

    publish_event.assert_called_once_with(
        EXECUTION_ID,
        "execution.status",
        {"status": "cancelling"},
    )


@pytest.mark.asyncio
async def test_cancel_returns_false_for_completed_execution():
    """cancel_execution on a completed execution returns the record unchanged (not False)."""
    record = _make_record("completed")
    svc = _make_service(record)

    result = await svc.cancel_execution(EXECUTION_ID)

    # Should return the record without changing it
    assert result is record
    assert record.status == "completed"
    # No commit should have happened (status not in pending/running)
    svc.db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_returns_none_for_missing_execution():
    """cancel_execution when execution not found → returns None."""
    db = MagicMock()
    db.commit = AsyncMock()
    svc = ExecutionService(db)
    svc.get_by_id = AsyncMock(return_value=None)

    result = await svc.cancel_execution("nonexistent-id")

    assert result is None


@pytest.mark.asyncio
async def test_cancel_works_without_redis():
    """cancel_execution without redis does not raise."""
    record = _make_record("pending")
    svc = _make_service(record, redis=None)

    result = await svc.cancel_execution(EXECUTION_ID)
    assert result.status == "cancelling"


@pytest.mark.asyncio
async def test_cancel_works_without_publish_event():
    """cancel_execution without publish_event does not raise."""
    record = _make_record("pending")
    svc = _make_service(record, publish_event=None)

    result = await svc.cancel_execution(EXECUTION_ID)
    assert result.status == "cancelling"


@pytest.mark.asyncio
async def test_cancel_flow_eventually_persists_cancelled_status():
    """Service-level cancel + engine completion should end in status='cancelled'."""
    execution_record = SimpleNamespace(
        id=EXECUTION_ID,
        status="running",
        workspace_id="ws-1",
        feature_id="test_cap",
        params={
            "brief": {
                "capability_id": "test_cap",
                "raw_message": "cancel this run",
                "workspace_id": "ws-1",
                "brief": {"topic": "cancel test"},
                "decisions": {},
            }
        },
    )

    db = _make_db_with_record(execution_record)
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock()
    publish_event = AsyncMock()

    execution_svc = ExecutionService(db, redis=redis_mock, publish_event=publish_event)
    execution_svc.get_by_id = AsyncMock(side_effect=[execution_record, execution_record])
    execution_svc.start_execution = AsyncMock()
    execution_svc.complete_execution = AsyncMock()

    result = await execution_svc.cancel_execution(EXECUTION_ID)
    assert result.status == "cancelling"

    cancelled_report = TaskReport(
        execution_id=EXECUTION_ID,
        capability_id="test_cap",
        status="cancelled",
        duration_seconds=1,
        narrative="Execution cancelled",
        outputs=[],
        errors=[],
        token_usage=None,
    )
    runtime = MagicMock()
    runtime.run_session = AsyncMock(return_value=cancelled_report)

    run_history_service = MagicMock()
    run_history_service.record = AsyncMock()

    engine = ExecutionEngineV2(
        runtime=runtime,
        execution_service=execution_svc,
        run_history_service=run_history_service,
    )

    await engine.run(EXECUTION_ID)

    execution_svc.complete_execution.assert_called_once()
    kwargs = execution_svc.complete_execution.call_args.kwargs
    assert kwargs["status"] == "cancelled"
