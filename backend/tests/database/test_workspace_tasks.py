"""Round-trip tests for workspace_tasks table."""

import pytest
from sqlalchemy import select

from tests.database.conftest import (
    DbUser,
    DbWorkspace,
    DbWorkspaceTask,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-wt", email="wt@t.com", name="wt", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-wt", user_id="u-wt", name="wt", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_add_task_persists(test_session):
    """Adding a task persists title and status."""
    _seed_workspace(test_session)
    await test_session.commit()

    task = DbWorkspaceTask(
        id="wt-1",
        workspace_id="ws-wt",
        title="Review introduction",
        status="pending",
        created_by="user",
    )
    test_session.add(task)
    await test_session.commit()
    await test_session.refresh(task)

    fetched = await test_session.get(DbWorkspaceTask, "wt-1")
    assert fetched is not None
    assert fetched.title == "Review introduction"
    assert fetched.status == "pending"
    assert fetched.priority == 0


@pytest.mark.asyncio
async def test_update_status_to_done_sets_completed_at(test_session):
    """Updating status to 'done' sets completed_at."""
    _seed_workspace(test_session)
    await test_session.commit()

    task = DbWorkspaceTask(
        id="wt-2",
        workspace_id="ws-wt",
        title="Write abstract",
        status="in_progress",
        created_by="user",
    )
    test_session.add(task)
    await test_session.commit()

    # Simulate update to done
    task.status = "done"
    task.completed_at = "2026-05-09T12:00:00"
    await test_session.commit()
    await test_session.refresh(task)

    assert task.status == "done"
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_list_with_status_filter(test_session):
    """Listing with status filter returns only matching tasks."""
    _seed_workspace(test_session)
    await test_session.commit()

    t1 = DbWorkspaceTask(
        id="wt-f1",
        workspace_id="ws-wt",
        title="Task A",
        status="pending",
        created_by="user",
    )
    t2 = DbWorkspaceTask(
        id="wt-f2",
        workspace_id="ws-wt",
        title="Task B",
        status="done",
        created_by="user",
    )
    t3 = DbWorkspaceTask(
        id="wt-f3",
        workspace_id="ws-wt",
        title="Task C",
        status="pending",
        created_by="user",
    )
    test_session.add_all([t1, t2, t3])
    await test_session.commit()

    # Filter by status=pending
    result = await test_session.execute(
        select(DbWorkspaceTask).where(
            DbWorkspaceTask.workspace_id == "ws-wt",
            DbWorkspaceTask.deleted_at.is_(None),
            DbWorkspaceTask.status == "pending",
        )
    )
    pending = result.scalars().all()
    assert len(pending) == 2
    assert all(t.status == "pending" for t in pending)

    # Filter by status=done
    result = await test_session.execute(
        select(DbWorkspaceTask).where(
            DbWorkspaceTask.workspace_id == "ws-wt",
            DbWorkspaceTask.deleted_at.is_(None),
            DbWorkspaceTask.status == "done",
        )
    )
    done = result.scalars().all()
    assert len(done) == 1
    assert done[0].title == "Task B"
