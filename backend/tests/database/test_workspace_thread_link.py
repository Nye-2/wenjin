"""Round-trip tests for the workspace thread_id 1:1 link.

These tests exercise actual SQLite constraint enforcement, not just ORM
metadata declarations.  The minimal SQLite-compatible models are provided by
tests/database/conftest.py (DbUser, DbThread, DbWorkspace).
"""

import pytest
from sqlalchemy.exc import IntegrityError

from tests.database.conftest import DbThread, DbUser, DbWorkspace


@pytest.mark.asyncio
async def test_workspace_thread_id_round_trips(test_session):
    """A workspace can store and retrieve a thread_id (DB round-trip)."""
    user = DbUser(id="u-1", email="t@t.com", name="t", hashed_password="x")
    test_session.add(user)
    thread = DbThread(id="tid-1", user_id="u-1", title="t")
    test_session.add(thread)
    workspace = DbWorkspace(
        id="ws-1",
        user_id="u-1",
        name="test",
        type="thesis",
        thread_id="tid-1",
    )
    test_session.add(workspace)
    await test_session.commit()

    fetched = await test_session.get(DbWorkspace, "ws-1")
    assert fetched is not None
    assert fetched.thread_id == "tid-1"


@pytest.mark.asyncio
async def test_workspace_thread_id_uniqueness_enforced(test_session):
    """Two workspaces cannot share the same thread_id (DB-enforced unique constraint)."""
    user = DbUser(id="u-2", email="t2@t.com", name="t2", hashed_password="x")
    test_session.add(user)
    thread = DbThread(id="tid-2", user_id="u-2", title="t")
    test_session.add(thread)
    ws1 = DbWorkspace(
        id="ws-2",
        user_id="u-2",
        name="a",
        type="thesis",
        thread_id="tid-2",
    )
    test_session.add(ws1)
    await test_session.commit()

    ws2 = DbWorkspace(
        id="ws-3",
        user_id="u-2",
        name="b",
        type="thesis",
        thread_id="tid-2",  # duplicate — must violate the unique constraint
    )
    test_session.add(ws2)

    with pytest.raises(IntegrityError):
        await test_session.commit()
