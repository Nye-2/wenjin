"""Round-trip tests for decisions table."""

import pytest
from sqlalchemy import select

from tests.database.conftest import (
    DbUser,
    DbWorkspace,
    DbDecision,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-dec", email="dec@t.com", name="dec", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-dec", user_id="u-dec", name="dec", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_set_and_get_active_single(test_session):
    """Setting a decision and reading get_active returns it."""
    _seed_workspace(test_session)
    await test_session.commit()

    d = DbDecision(
        id="dec-1",
        workspace_id="ws-dec",
        key="citation_style",
        value="MLA",
        extracted_by="user",
    )
    test_session.add(d)
    await test_session.commit()

    result = await test_session.execute(
        select(DbDecision).where(
            DbDecision.workspace_id == "ws-dec",
            DbDecision.deleted_at.is_(None),
            DbDecision.superseded_by.is_(None),
        )
    )
    active = {row.key: row.value for row in result.scalars().all()}
    assert active == {"citation_style": "MLA"}


@pytest.mark.asyncio
async def test_supersede_replaces_active(test_session):
    """Setting a new value supersedes the old decision."""
    _seed_workspace(test_session)
    await test_session.commit()

    old = DbDecision(
        id="dec-old",
        workspace_id="ws-dec",
        key="citation_style",
        value="MLA",
        extracted_by="user",
    )
    test_session.add(old)
    await test_session.commit()

    # Create new decision and supersede old
    new = DbDecision(
        id="dec-new",
        workspace_id="ws-dec",
        key="citation_style",
        value="APA",
        extracted_by="user",
    )
    test_session.add(new)
    await test_session.flush()  # flush so new.id is available
    old.superseded_by = "dec-new"
    await test_session.commit()

    # Verify: old has superseded_by set
    await test_session.refresh(old)
    assert old.superseded_by == "dec-new"

    # Verify: get_active returns only the new one
    result = await test_session.execute(
        select(DbDecision).where(
            DbDecision.workspace_id == "ws-dec",
            DbDecision.deleted_at.is_(None),
            DbDecision.superseded_by.is_(None),
        )
    )
    active = {row.key: row.value for row in result.scalars().all()}
    assert active == {"citation_style": "APA"}


@pytest.mark.asyncio
async def test_delete_excludes_from_active(test_session):
    """After soft-delete, get_active excludes the decision."""
    _seed_workspace(test_session)
    await test_session.commit()

    d = DbDecision(
        id="dec-del",
        workspace_id="ws-dec",
        key="tone",
        value="formal",
        extracted_by="user",
    )
    test_session.add(d)
    await test_session.commit()

    d.deleted_at = "2026-05-09T00:00:00"
    await test_session.commit()

    result = await test_session.execute(
        select(DbDecision).where(
            DbDecision.workspace_id == "ws-dec",
            DbDecision.deleted_at.is_(None),
            DbDecision.superseded_by.is_(None),
        )
    )
    assert result.scalars().all() == []
