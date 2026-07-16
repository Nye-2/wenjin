"""Round-trip tests for workspace_settings defaults, update, and idempotency.

These tests exercise actual SQLite database behavior using the minimal
SQLite-compatible models from tests/database/conftest.py.
"""

import pytest
from sqlalchemy import select

from tests.database.conftest import DbUser, DbWorkspace, DbWorkspaceSettings


@pytest.mark.asyncio
async def test_get_or_create_default(test_session):
    """get_or_create on a new workspace returns correct defaults."""
    user = DbUser(id="u-1", email="t@t.com", name="t", hashed_password="x")
    test_session.add(user)
    workspace = DbWorkspace(
        id="ws-1", user_id="u-1", name="test", type="thesis",
    )
    test_session.add(workspace)
    await test_session.commit()

    # Simulate get_or_create: select first, create if missing
    result = await test_session.execute(
        select(DbWorkspaceSettings).where(
            DbWorkspaceSettings.workspace_id == "ws-1"
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = DbWorkspaceSettings(workspace_id="ws-1")
        test_session.add(row)
        await test_session.commit()
        await test_session.refresh(row)

    assert row.workspace_id == "ws-1"
    assert row.reasoning_effort == "xhigh"
    assert row.auto_compact_threshold == pytest.approx(0.8)
    assert row.default_model is None
    assert row.metadata_json == {}


@pytest.mark.asyncio
async def test_update_setting(test_session):
    """Updating default_model persists correctly."""
    user = DbUser(id="u-2", email="t2@t.com", name="t2", hashed_password="x")
    test_session.add(user)
    workspace = DbWorkspace(
        id="ws-2", user_id="u-2", name="test", type="thesis",
    )
    test_session.add(workspace)
    await test_session.commit()

    # Create the settings row
    row = DbWorkspaceSettings(workspace_id="ws-2")
    test_session.add(row)
    await test_session.commit()
    await test_session.refresh(row)

    # Update default_model
    row.default_model = "claude-opus-4-7"
    await test_session.commit()
    await test_session.refresh(row)

    # Verify persisted
    fetched = await test_session.get(DbWorkspaceSettings, "ws-2")
    assert fetched is not None
    assert fetched.default_model == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_get_or_create_idempotent(test_session):
    """Calling get_or_create twice returns the same row (no duplicate)."""
    user = DbUser(id="u-3", email="t3@t.com", name="t3", hashed_password="x")
    test_session.add(user)
    workspace = DbWorkspace(
        id="ws-3", user_id="u-3", name="test", type="thesis",
    )
    test_session.add(workspace)
    await test_session.commit()

    # First get_or_create
    result = await test_session.execute(
        select(DbWorkspaceSettings).where(
            DbWorkspaceSettings.workspace_id == "ws-3"
        )
    )
    row1 = result.scalar_one_or_none()
    if row1 is None:
        row1 = DbWorkspaceSettings(workspace_id="ws-3")
        test_session.add(row1)
        await test_session.commit()
        await test_session.refresh(row1)

    # Second get_or_create — must return the same row
    result = await test_session.execute(
        select(DbWorkspaceSettings).where(
            DbWorkspaceSettings.workspace_id == "ws-3"
        )
    )
    row2 = result.scalar_one_or_none()
    if row2 is None:
        row2 = DbWorkspaceSettings(workspace_id="ws-3")
        test_session.add(row2)
        await test_session.commit()
        await test_session.refresh(row2)

    assert row1.workspace_id == row2.workspace_id

    # Only one row exists in the table
    count_result = await test_session.execute(
        select(DbWorkspaceSettings).where(
            DbWorkspaceSettings.workspace_id == "ws-3"
        )
    )
    all_rows = count_result.scalars().all()
    assert len(all_rows) == 1
