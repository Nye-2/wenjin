"""Test fixtures for task system tests.

This module provides:
- In-memory SQLite database for testing with SQLite-compatible TaskRecord model
- Mock Redis client for testing Redis operations
- Test fixtures for TaskStore and TaskService
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

# ============ Test Database Models (SQLite-compatible) ============

class TestBase(DeclarativeBase):
    """Base class for test models."""
    pass


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


class FixtureTaskRecord(TestBase):
    """Test TaskRecord model compatible with SQLite."""
    __tablename__ = "task_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Structured context fields — populated from payload at task creation
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    mission_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Request
    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Response
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class _TestTaskDataServiceClient:
    def __init__(self, session: AsyncSession, record_model: type[FixtureTaskRecord]) -> None:
        from src.dataservice.task_api import TaskDataService

        self._service = TaskDataService(
            session,
            autocommit=True,
            record_model=record_model,
        )

    async def create_task_record(self, command):
        return await self._service.create_task_record(**command.model_dump())

    async def create_task_record_guarded(self, command):
        return await self._service.create_task_record_guarded(**command.model_dump())

    async def get_task_record(self, task_id: str):
        return await self._service.get_task_record(task_id)

    async def update_task_record(self, task_id: str, command):
        return await self._service.update_task_record(
            task_id,
            **command.model_dump(exclude_unset=True),
        )

    async def list_user_task_records(
        self,
        *,
        user_id: str,
        status=None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
    ):
        return await self._service.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
            workspace_id=workspace_id,
        )

    async def count_active_task_records(self, *, user_id: str, active_statuses: list[str]):
        return await self._service.count_active_tasks(
            user_id=user_id,
            active_statuses=active_statuses,
        )


# ============ Mock Redis Client ============

class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data: dict[str, dict[str, str]] = {}
        self._client = AsyncMock()

    async def connect(self) -> None:
        """Mock connect."""
        pass

    async def disconnect(self) -> None:
        """Mock disconnect."""
        pass

    @property
    def client(self) -> AsyncMock:
        """Get mock Redis client."""
        return self._client

    def _setup_mock(self):
        """Setup mock methods."""
        async def mock_hset(key: str, mapping: dict):
            if key not in self._data:
                self._data[key] = {}
            self._data[key].update(mapping)

        async def mock_hgetall(key: str) -> dict:
            return self._data.get(key, {})

        async def mock_delete(key: str):
            self._data.pop(key, None)

        async def mock_expire(key: str, ttl: int):
            pass  # TTL not implemented in mock

        self._client.hset = mock_hset
        self._client.hgetall = mock_hgetall
        self._client.delete = mock_delete
        self._client.expire = mock_expire


# ============ Fixtures ============

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine with in-memory SQLite."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def mock_redis():
    """Create a mock Redis client."""
    redis = MockRedisClient()
    redis._setup_mock()
    await redis.connect()
    yield redis
    await redis.disconnect()


@pytest_asyncio.fixture(scope="function")
async def task_store(test_session, mock_redis):
    """Create TaskStore instance with test fixtures."""
    from src.task.store import TaskStore

    store = TaskStore(
        mock_redis,
        dataservice=_TestTaskDataServiceClient(test_session, FixtureTaskRecord),
    )
    yield store
