"""Tests for the v2 workspace migration script.

Uses in-memory SQLite with mock models mirroring the production schema.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from scripts.migrate_workspace_v2 import migrate, MigrationResult


# ---------------------------------------------------------------------------
# SQLite-compatible mock models for migration tests
# ---------------------------------------------------------------------------

class _Base(DeclarativeBase):
    pass


class _User(_Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)


class _Thread(_Base):
    __tablename__ = "threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)


class _Workspace(_Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("threads.id", ondelete="SET NULL"),
        nullable=True, unique=True,
    )


class _WorkspaceReference(_Base):
    __tablename__ = "workspace_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )


class _Artifact(_Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )


class _LibraryItem(_Base):
    __tablename__ = "library_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cited_in_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _DocumentV2(_Base):
    __tablename__ = "documents_v2"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


# ---------------------------------------------------------------------------
# Shared model dict injected into migrate()
# ---------------------------------------------------------------------------

_MOCK_MODELS = {
    "Thread": _Thread,
    "Workspace": _Workspace,
    "WorkspaceReference": _WorkspaceReference,
    "LibraryItem": _LibraryItem,
    "Artifact": _Artifact,
    "DocumentV2": _DocumentV2,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def _db_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async SQLite session for migration tests."""
    factory = async_sessionmaker(
        _db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


def _make_user(**kwargs):
    defaults = {
        "email": "test@example.com",
        "name": "Test User",
        "hashed_password": "fakehash",
    }
    defaults.update(kwargs)
    return _User(**defaults)


def _make_thread(user_id: str, **kwargs):
    defaults = {
        "user_id": user_id,
        "title": "Test thread",
    }
    defaults.update(kwargs)
    return _Thread(**defaults)


def _make_workspace(user_id: str, **kwargs):
    defaults = {
        "user_id": user_id,
        "name": "Test workspace",
        "type": "thesis",
    }
    defaults.update(kwargs)
    return _Workspace(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry-run should report changes but not persist them."""

    @pytest.mark.asyncio
    async def test_dry_run_no_commit_on_empty_db(self, async_session):
        """Dry run on empty DB succeeds with zero changes."""
        result = await migrate(async_session, dry_run=True, models=_MOCK_MODELS)
        assert isinstance(result, MigrationResult)
        assert result.workspaces_migrated == 0
        assert result.library_items_migrated == 0
        assert result.documents_migrated == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_dry_run_does_not_create_workspaces(self, async_session):
        """Dry run should not persist workspace records."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        thread = _make_thread(user.id)
        async_session.add(thread)
        await async_session.commit()

        result = await migrate(async_session, dry_run=True, models=_MOCK_MODELS)
        assert result.workspaces_migrated == 1

        # Verify no workspace records were actually created
        count_q = await async_session.execute(
            select(func.count(_Workspace.id))
        )
        assert count_q.scalar() == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_create_library_items(self, async_session):
        """Dry run should not persist library item records."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        ws = _make_workspace(user.id)
        async_session.add(ws)
        await async_session.commit()

        ref = _WorkspaceReference(
            workspace_id=ws.id,
            title="Test Paper",
            authors=["Author A"],
            year=2024,
            venue="Nature",
            citation_key="author2024test",
            source_type="manual",
        )
        async_session.add(ref)
        await async_session.commit()

        result = await migrate(async_session, dry_run=True, models=_MOCK_MODELS)
        assert result.library_items_migrated == 1

        count_q = await async_session.execute(
            select(func.count(_LibraryItem.id))
        )
        assert count_q.scalar() == 0


class TestCommitCreatesRecords:
    """Actual run should create records for orphaned legacy data."""

    @pytest.mark.asyncio
    async def test_creates_workspaces_for_orphaned_threads(self, async_session):
        """Threads without a workspace.thread_id link get a new workspace."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        thread1 = _make_thread(user.id, title="Thread 1")
        thread2 = _make_thread(user.id, title="Thread 2")
        async_session.add_all([thread1, thread2])
        await async_session.commit()

        result = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result.workspaces_migrated == 2
        assert result.errors == []

        count_q = await async_session.execute(
            select(func.count(_Workspace.id))
        )
        assert count_q.scalar() == 2

    @pytest.mark.asyncio
    async def test_skips_threads_already_linked(self, async_session):
        """Threads already linked as workspace.thread_id should be skipped."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        thread = _make_thread(user.id)
        async_session.add(thread)
        await async_session.commit()

        # Create a workspace already linked to this thread
        ws = _make_workspace(user.id, thread_id=thread.id)
        async_session.add(ws)
        await async_session.commit()

        result = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result.workspaces_migrated == 0
        assert result.skipped_existing >= 1

    @pytest.mark.asyncio
    async def test_creates_library_items_from_references(self, async_session):
        """WorkspaceReference records should be migrated to LibraryItem."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        ws = _make_workspace(user.id)
        async_session.add(ws)
        await async_session.commit()

        ref1 = _WorkspaceReference(
            workspace_id=ws.id,
            title="Paper Alpha",
            authors=["Alice", "Bob"],
            year=2024,
            venue="Science",
            doi="10.1234/test",
            citation_key="alpha2024",
            source_type="semantic_scholar",
        )
        ref2 = _WorkspaceReference(
            workspace_id=ws.id,
            title="Paper Beta",
            authors=["Charlie"],
            year=2023,
            citation_key="beta2023",
            source_type="manual",
        )
        async_session.add_all([ref1, ref2])
        await async_session.commit()

        result = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result.library_items_migrated == 2

        count_q = await async_session.execute(
            select(func.count(_LibraryItem.id))
        )
        assert count_q.scalar() == 2

    @pytest.mark.asyncio
    async def test_creates_documents_from_artifacts(self, async_session):
        """Artifact records should be migrated to DocumentV2."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        ws = _make_workspace(user.id)
        async_session.add(ws)
        await async_session.commit()

        artifact = _Artifact(
            workspace_id=ws.id,
            type="research_idea",
            title="My Research Idea",
            content={"text": "A novel approach"},
            created_by_skill="brainstorm",
            version=1,
            status="draft",
        )
        async_session.add(artifact)
        await async_session.commit()

        result = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result.documents_migrated == 1

        count_q = await async_session.execute(
            select(func.count(_DocumentV2.id))
        )
        assert count_q.scalar() == 1


class TestIdempotent:
    """Running the migration twice should not duplicate records."""

    @pytest.mark.asyncio
    async def test_idempotent_workspaces(self, async_session):
        """Running twice should skip already-migrated threads."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        thread = _make_thread(user.id)
        async_session.add(thread)
        await async_session.commit()

        # First run
        result1 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result1.workspaces_migrated == 1

        # Second run
        result2 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result2.workspaces_migrated == 0
        assert result2.skipped_existing >= 1

        # Confirm no duplicates
        count_q = await async_session.execute(
            select(func.count(_Workspace.id))
        )
        assert count_q.scalar() == 1

    @pytest.mark.asyncio
    async def test_idempotent_library_items(self, async_session):
        """Running twice should skip already-migrated references."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        ws = _make_workspace(user.id)
        async_session.add(ws)
        await async_session.commit()

        ref = _WorkspaceReference(
            workspace_id=ws.id,
            title="Idempotent Paper",
            authors=["Author"],
            citation_key="idempotent2024",
            source_type="manual",
        )
        async_session.add(ref)
        await async_session.commit()

        result1 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result1.library_items_migrated == 1

        result2 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result2.library_items_migrated == 0
        assert result2.skipped_existing >= 1

    @pytest.mark.asyncio
    async def test_idempotent_documents(self, async_session):
        """Running twice should skip already-migrated artifacts."""
        user = _make_user()
        async_session.add(user)
        await async_session.commit()

        ws = _make_workspace(user.id)
        async_session.add(ws)
        await async_session.commit()

        artifact = _Artifact(
            workspace_id=ws.id,
            type="methodology",
            title="Method v1",
            content={"sections": []},
            version=1,
            status="draft",
        )
        async_session.add(artifact)
        await async_session.commit()

        result1 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result1.documents_migrated == 1

        result2 = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result2.documents_migrated == 0
        assert result2.skipped_existing >= 1


class TestEmptyDatabase:
    """Migration on empty DB should succeed cleanly."""

    @pytest.mark.asyncio
    async def test_empty_db_no_changes(self, async_session):
        """No legacy data means zero migrations."""
        result = await migrate(async_session, dry_run=False, models=_MOCK_MODELS)
        assert result.workspaces_migrated == 0
        assert result.library_items_migrated == 0
        assert result.documents_migrated == 0
        assert result.skipped_existing == 0
        assert result.errors == []
