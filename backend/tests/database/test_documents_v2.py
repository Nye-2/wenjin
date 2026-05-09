"""Round-trip tests for documents_v2 table."""

import pytest
from sqlalchemy import select

from tests.database.conftest import (
    DbUser,
    DbWorkspace,
    DbDocumentV2,
)


def _seed_workspace(test_session):
    """Create a user + workspace for FK integrity."""
    user = DbUser(id="u-doc", email="doc@t.com", name="doc", hashed_password="x")
    test_session.add(user)
    ws = DbWorkspace(id="ws-doc", user_id="u-doc", name="doc", type="thesis")
    test_session.add(ws)
    return ws


@pytest.mark.asyncio
async def test_add_document_version_1(test_session):
    """Adding a document starts with version=1."""
    _seed_workspace(test_session)
    await test_session.commit()

    doc = DbDocumentV2(
        id="doc-1",
        workspace_id="ws-doc",
        name="draft.tex",
        kind="draft",
        added_by="user",
    )
    test_session.add(doc)
    await test_session.commit()
    await test_session.refresh(doc)

    fetched = await test_session.get(DbDocumentV2, "doc-1")
    assert fetched is not None
    assert fetched.version == 1
    assert fetched.name == "draft.tex"
    assert fetched.parent_id is None


@pytest.mark.asyncio
async def test_commit_version_sets_parent_and_increments(test_session):
    """commit_version creates v2 with parent_id pointing to v1."""
    _seed_workspace(test_session)
    await test_session.commit()

    v1 = DbDocumentV2(
        id="doc-v1",
        workspace_id="ws-doc",
        name="paper.tex",
        kind="draft",
        version=1,
        added_by="user",
    )
    test_session.add(v1)
    await test_session.commit()

    # Simulate commit_version: create v2 with parent_id
    v2 = DbDocumentV2(
        id="doc-v2",
        workspace_id="ws-doc",
        name="paper.tex",
        kind="draft",
        parent_id="doc-v1",
        version=v1.version + 1,
        added_by="user",
    )
    test_session.add(v2)
    await test_session.commit()
    await test_session.refresh(v2)

    assert v2.version == 2
    assert v2.parent_id == "doc-v1"


@pytest.mark.asyncio
async def test_soft_delete_excludes_from_list(test_session):
    """After soft-delete, list returns empty."""
    _seed_workspace(test_session)
    await test_session.commit()

    doc = DbDocumentV2(
        id="doc-del",
        workspace_id="ws-doc",
        name="to_delete.tex",
        kind="draft",
        added_by="user",
    )
    test_session.add(doc)
    await test_session.commit()

    doc.deleted_at = "2026-05-09T00:00:00"
    await test_session.commit()

    result = await test_session.execute(
        select(DbDocumentV2).where(
            DbDocumentV2.workspace_id == "ws-doc",
            DbDocumentV2.deleted_at.is_(None),
        )
    )
    assert result.scalars().all() == []
