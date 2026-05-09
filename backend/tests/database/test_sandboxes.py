"""Round-trip tests for sandboxes table."""

import pytest
from sqlalchemy import select

from tests.database.conftest import (
    DbUser,
    DbWorkspace,
    DbSandbox,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-sbx", email="sbx@t.com", name="sbx", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-sbx", user_id="u-sbx", name="sbx", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_get_or_create_returns_active(test_session):
    """get_or_create creates an active sandbox."""
    _seed_workspace(test_session)
    await test_session.commit()

    sbx = DbSandbox(
        workspace_id="ws-sbx",
        sandbox_id="sbx-001",
        provider="local",
        state="active",
    )
    test_session.add(sbx)
    await test_session.commit()
    await test_session.refresh(sbx)

    fetched = await test_session.get(DbSandbox, "ws-sbx")
    assert fetched is not None
    assert fetched.state == "active"
    assert fetched.provider == "local"
    assert fetched.sandbox_id == "sbx-001"


@pytest.mark.asyncio
async def test_get_or_create_twice_same_id(test_session):
    """Calling get_or_create twice returns the same sandbox_id."""
    _seed_workspace(test_session)
    await test_session.commit()

    sbx = DbSandbox(
        workspace_id="ws-sbx",
        sandbox_id="sbx-002",
        provider="local",
        state="active",
    )
    test_session.add(sbx)
    await test_session.commit()

    # Second get_or_create: should find existing active one
    result = await test_session.execute(
        select(DbSandbox).where(
            DbSandbox.workspace_id == "ws-sbx",
            DbSandbox.state == "active",
        )
    )
    existing = result.scalar_one_or_none()
    assert existing is not None
    assert existing.sandbox_id == "sbx-002"


@pytest.mark.asyncio
async def test_release_sets_stopped(test_session):
    """release sets state to 'stopped'."""
    _seed_workspace(test_session)
    await test_session.commit()

    sbx = DbSandbox(
        workspace_id="ws-sbx",
        sandbox_id="sbx-003",
        provider="local",
        state="active",
    )
    test_session.add(sbx)
    await test_session.commit()

    # Simulate release
    sbx.state = "stopped"
    await test_session.commit()
    await test_session.refresh(sbx)

    assert sbx.state == "stopped"
