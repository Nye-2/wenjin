"""Database-layer test fixtures.

Provides an async in-memory SQLite session for round-trip / constraint tests.
The models declared here mirror only the columns needed for database contract
tests and are intentionally SQLite-compatible (no JSONB, no PostgreSQL types).
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import JSON, REAL, Boolean, ForeignKey, String, func
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
    metadata_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.now(), onupdate=func.now(),
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
