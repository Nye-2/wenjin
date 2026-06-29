"""Database-layer test fixtures.

Provides an async in-memory SQLite session for round-trip / constraint tests.
The models declared here mirror only the columns needed for database contract
tests and are intentionally SQLite-compatible (no JSONB, no PostgreSQL types).
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import JSON, REAL, BigInteger, Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Minimal SQLite-compatible schema (mirrors production columns under test)
# ---------------------------------------------------------------------------

class _Base(DeclarativeBase):
    """Isolated declarative base for database contract tests."""


class _User(_Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)


class _Thread(_Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)


class _Workspace(_Base):
    """Mirrors the columns declared in src.database.models.workspace.Workspace
    that are relevant to the thread_id 1:1 link contract.
    """

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,   # ← the constraint under test
    )


class _WorkspaceSettings(_Base):
    """SQLite-compatible mirror of WorkspaceSettings for database contract tests.

    Uses JSON instead of JSONB since SQLite does not support JSONB.
    """

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    thinking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    sandbox_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="local",
    )
    auto_compact_threshold: Mapped[float] = mapped_column(
        REAL, nullable=False, default=0.8,
    )
    capability_overrides: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    settings_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class _LibraryItem(_Base):
    """SQLite-compatible mirror of LibraryItem."""

    __tablename__ = "library_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cited_in_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _DocumentV2(_Base):
    """SQLite-compatible mirror of DocumentV2."""

    __tablename__ = "documents_v2"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents_v2.id"), nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _Decision(_Base):
    """SQLite-compatible mirror of Decision."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False, default=1.0)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extracted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("decisions.id"), nullable=True,
    )
    source_review_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_review_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _RunHistory(_Base):
    """SQLite-compatible mirror of RunHistory."""

    __tablename__ = "run_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _Sandbox(_Base):
    """SQLite-compatible mirror of Sandbox."""

    __tablename__ = "sandboxes"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True,
    )
    sandbox_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_active_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )


class _WorkspaceTask(_Base):
    """SQLite-compatible mirror of WorkspaceTask."""

    __tablename__ = "workspace_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    related_execution_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    source_review_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_review_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    completed_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class _Capability(_Base):
    """SQLite-compatible mirror of Capability (composite PK: id, workspace_type)."""

    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_phrases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_decisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    brief_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    graph_template: Mapped[dict] = mapped_column(JSON, nullable=False)
    ui_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runtime: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dashboard_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class _CapabilitySkill(_Base):
    """SQLite-compatible mirror of CapabilitySkill."""

    __tablename__ = "capability_skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subagent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    allowed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class _AuditLog(_Base):
    """SQLite-compatible mirror of AuditLog."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(),
    )


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
async def test_session(_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async SQLite session for database round-trip tests."""
    factory = async_sessionmaker(
        _db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


# Expose helpers so test modules can import them without re-importing conftest
DbUser = _User
DbThread = _Thread
DbWorkspace = _Workspace
DbWorkspaceSettings = _WorkspaceSettings
DbLibraryItem = _LibraryItem
DbDocumentV2 = _DocumentV2
DbDecision = _Decision
DbRunHistory = _RunHistory
DbSandbox = _Sandbox
DbWorkspaceTask = _WorkspaceTask
DbAuditLog = _AuditLog
DbCapability = _Capability
DbCapabilitySkill = _CapabilitySkill
