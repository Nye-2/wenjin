"""Round-trip tests for memory_facts table."""

import pytest
from sqlalchemy import select, func

from tests.database.conftest import (
    DbUser,
    DbWorkspace,
    DbMemoryFact,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-mem", email="mem@t.com", name="mem", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-mem", user_id="u-mem", name="mem", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_add_facts_and_evict(test_session):
    """Adding 105 facts then evicting to 100 leaves exactly 100."""
    _seed_workspace(test_session)
    await test_session.commit()

    # Add 105 facts
    for i in range(105):
        test_session.add(
            DbMemoryFact(
                id=f"mf-{i:03d}",
                workspace_id="ws-mem",
                category="context",
                content=f"Fact {i}",
                reference_count=i % 10,  # varying reference counts
            )
        )
    await test_session.commit()

    # Verify 105 exist
    count_result = await test_session.execute(
        select(func.count()).select_from(DbMemoryFact).where(
            DbMemoryFact.workspace_id == "ws-mem",
            DbMemoryFact.deleted_at.is_(None),
        )
    )
    assert count_result.scalar_one() == 105

    # Evict: find lowest-priority 5 and soft-delete
    result = await test_session.execute(
        select(DbMemoryFact)
        .where(
            DbMemoryFact.workspace_id == "ws-mem",
            DbMemoryFact.deleted_at.is_(None),
        )
        .order_by(DbMemoryFact.reference_count.asc(), DbMemoryFact.created_at.asc())
        .limit(5)
    )
    victims = result.scalars().all()
    for v in victims:
        v.deleted_at = "2026-05-09T00:00:00"
    await test_session.commit()

    # Verify exactly 100 remain
    count_result = await test_session.execute(
        select(func.count()).select_from(DbMemoryFact).where(
            DbMemoryFact.workspace_id == "ws-mem",
            DbMemoryFact.deleted_at.is_(None),
        )
    )
    assert count_result.scalar_one() == 100


@pytest.mark.asyncio
async def test_mark_referenced_increments_count(test_session):
    """mark_referenced increments reference_count."""
    _seed_workspace(test_session)
    await test_session.commit()

    mf = DbMemoryFact(
        id="mf-ref",
        workspace_id="ws-mem",
        category="writing_style",
        content="Use Oxford comma",
        reference_count=0,
    )
    test_session.add(mf)
    await test_session.commit()

    # Simulate mark_referenced
    mf.reference_count = (mf.reference_count or 0) + 1
    mf.last_referenced_at = "2026-05-09T12:00:00"
    await test_session.commit()
    await test_session.refresh(mf)

    assert mf.reference_count == 1
    assert mf.last_referenced_at is not None
