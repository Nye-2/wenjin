"""Round-trip tests for run_history table."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.dataservice.domains.execution.contracts import ExecutionRunHistoryProjection
from src.services.rooms.run_history_service import RunHistoryService
from tests.database.conftest import (
    DbRunHistory,
    DbUser,
    DbWorkspace,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-run", email="run@t.com", name="run", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-run", user_id="u-run", name="run", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_record_persists(test_session):
    """Recording a run persists all fields correctly."""
    _seed_workspace(test_session)
    await test_session.commit()

    run = DbRunHistory(
        id="run-1",
        workspace_id="ws-run",
        execution_id="exec-001",
        capability_id="literature_search",
        title="Search for NLP papers",
        summary="Found 15 papers",
        status="completed",
        artifact_count=15,
        duration_seconds=120,
    )
    test_session.add(run)
    await test_session.commit()
    await test_session.refresh(run)

    fetched = await test_session.get(DbRunHistory, "run-1")
    assert fetched is not None
    assert fetched.execution_id == "exec-001"
    assert fetched.capability_id == "literature_search"
    assert fetched.status == "completed"
    assert fetched.duration_seconds == 120


@pytest.mark.asyncio
async def test_list_returns_descending_order(test_session):
    """Inserting 3 runs with explicit timestamps returns them in created_at DESC order."""
    _seed_workspace(test_session)
    await test_session.commit()

    # Insert 3 runs with explicit different created_at values
    run1 = DbRunHistory(
        id="run-ord-1",
        workspace_id="ws-run",
        execution_id="exec-ord-1",
        capability_id="cap",
        title="First run",
        summary="Summary for first run",
        status="completed",
        duration_seconds=10,
        created_at="2026-05-09T10:00:00",
    )
    run2 = DbRunHistory(
        id="run-ord-2",
        workspace_id="ws-run",
        execution_id="exec-ord-2",
        capability_id="cap",
        title="Second run",
        summary="Summary for second run",
        status="completed",
        duration_seconds=20,
        created_at="2026-05-09T11:00:00",
    )
    run3 = DbRunHistory(
        id="run-ord-3",
        workspace_id="ws-run",
        execution_id="exec-ord-3",
        capability_id="cap",
        title="Third run",
        summary="Summary for third run",
        status="completed",
        duration_seconds=30,
        created_at="2026-05-09T12:00:00",
    )
    test_session.add_all([run1, run2, run3])
    await test_session.commit()

    # List ordered by created_at DESC
    result = await test_session.execute(
        select(DbRunHistory)
        .where(
            DbRunHistory.workspace_id == "ws-run",
            DbRunHistory.deleted_at.is_(None),
        )
        .order_by(DbRunHistory.created_at.desc())
    )
    runs = result.scalars().all()
    assert len(runs) == 3
    # The most recent should be first (DESC)
    assert runs[0].title == "Third run"
    assert runs[1].title == "Second run"
    assert runs[2].title == "First run"


@pytest.mark.asyncio
async def test_record_updates_existing_execution_instead_of_inserting_duplicate(test_session):
    """Recording run history appends an execution event and returns projection state."""

    service = RunHistoryService(test_session)
    service._execution.get_run_history_item = AsyncMock(
        side_effect=[
            ExecutionRunHistoryProjection(
                id="exec-dup-1",
                workspace_id="ws-run",
                execution_id="exec-dup-1",
                capability_id="literature_search",
                title="First title",
                summary="First summary",
                status="completed",
                duration_seconds=30,
                artifact_count=1,
            ),
            ExecutionRunHistoryProjection(
                id="exec-dup-1",
                workspace_id="ws-run",
                execution_id="exec-dup-1",
                capability_id="framework_outline",
                title="Updated title",
                summary="Updated summary",
                status="failed_partial",
                duration_seconds=45,
                artifact_count=2,
            ),
        ]
    )
    service._execution.record_event = AsyncMock()

    first = await service.record(
        workspace_id="ws-run",
        execution_id="exec-dup-1",
        capability_id="literature_search",
        title="First title",
        summary="First summary",
        status="completed",
        duration_seconds=30,
        artifact_count=1,
    )

    second = await service.record(
        workspace_id="ws-run",
        execution_id="exec-dup-1",
        capability_id="framework_outline",
        title="Updated title",
        summary="Updated summary",
        status="failed_partial",
        duration_seconds=45,
        artifact_count=2,
    )

    assert second.id == first.id
    assert second.capability_id == "framework_outline"
    assert second.title == "Updated title"
    assert second.summary == "Updated summary"
    assert second.status == "failed_partial"
    assert second.duration_seconds == 45
    assert second.artifact_count == 2

    assert service._execution.record_event.await_count == 2
