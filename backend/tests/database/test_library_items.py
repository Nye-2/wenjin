"""Round-trip tests for library_items table."""

import pytest
from sqlalchemy import func, select

from tests.database.conftest import (
    DbLibraryItem,
    DbUser,
    DbWorkspace,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-lib", email="lib@t.com", name="lib", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-lib", user_id="u-lib", name="lib", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_add_library_item(test_session):
    """Adding a library item persists id and title."""
    _seed_workspace(test_session)
    await test_session.commit()

    item = DbLibraryItem(
        id="li-1",
        workspace_id="ws-lib",
        item_type="article",
        title="Deep Learning for NLP",
        added_by="user",
    )
    test_session.add(item)
    await test_session.commit()
    await test_session.refresh(item)

    fetched = await test_session.get(DbLibraryItem, "li-1")
    assert fetched is not None
    assert fetched.title == "Deep Learning for NLP"
    assert fetched.item_type == "article"
    assert fetched.authors == []
    assert fetched.tags == []


@pytest.mark.asyncio
async def test_bulk_add_and_count(test_session):
    """Bulk-adding 5 items results in 5 non-deleted rows."""
    _seed_workspace(test_session)
    await test_session.commit()

    for i in range(5):
        test_session.add(
            DbLibraryItem(
                id=f"li-bulk-{i}",
                workspace_id="ws-lib",
                item_type="article",
                title=f"Paper {i}",
                added_by="user",
            )
        )
    await test_session.commit()

    count_result = await test_session.execute(
        select(func.count()).select_from(DbLibraryItem).where(
            DbLibraryItem.workspace_id == "ws-lib",
            DbLibraryItem.deleted_at.is_(None),
        )
    )
    assert count_result.scalar_one() == 5


@pytest.mark.asyncio
async def test_soft_delete_excludes_from_list(test_session):
    """After soft-delete, list returns empty."""
    _seed_workspace(test_session)
    await test_session.commit()

    item = DbLibraryItem(
        id="li-del",
        workspace_id="ws-lib",
        item_type="book",
        title="To Delete",
        added_by="user",
    )
    test_session.add(item)
    await test_session.commit()

    # Soft delete
    item.deleted_at = "2026-05-09T00:00:00"
    await test_session.commit()

    result = await test_session.execute(
        select(DbLibraryItem).where(
            DbLibraryItem.workspace_id == "ws-lib",
            DbLibraryItem.deleted_at.is_(None),
        )
    )
    assert result.scalars().all() == []
