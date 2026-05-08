"""Tests for WorkspaceRunService."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.workspace_run import WorkspaceRunRow
from src.services.workspace_run_service import WorkspaceRunService


@pytest.fixture
def db_session():
    """Mock async database session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_create_run_uses_supplied_id(db_session):
    svc = WorkspaceRunService(db_session)
    run_id = await svc.create_run(
        run_id="es-1", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC),
    )
    assert run_id == "es-1"
    assert db_session.add.called
    added = db_session.add.call_args[0][0]
    assert isinstance(added, WorkspaceRunRow)
    assert added.id == "es-1"
    db_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_run_writes_result_card(db_session):
    row = WorkspaceRunRow(
        id="es-2", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC), status="running",
    )
    db_session.get = AsyncMock(return_value=row)
    svc = WorkspaceRunService(db_session)
    await svc.complete_run("es-2", result_card={"tldr": "x"}, stats={"tokens": 100})
    assert row.status == "completed"
    assert row.result_card["tldr"] == "x"
    db_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_soft_delete(db_session):
    row = WorkspaceRunRow(
        id="es-3", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC), status="running",
    )
    db_session.get = AsyncMock(return_value=row)

    svc = WorkspaceRunService(db_session)
    await svc.delete_run("es-3")
    assert row.deleted_at is not None

    # get_run should hide deleted rows
    assert await svc.get_run("es-3") is None

    # list_runs with include_deleted=True should still return it
    result_mock = MagicMock()
    result_mock.scalars.return_value = [row]
    db_session.execute = AsyncMock(return_value=result_mock)
    listed = await svc.list_runs(thread_id="th1", include_deleted=True)
    assert any(r.id == "es-3" for r in listed)
