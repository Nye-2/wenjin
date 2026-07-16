"""Tests for database session initialization helpers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


class _FakeConnection:
    def __init__(self) -> None:
        self.dialect = SimpleNamespace(name="postgresql")
        self.executed: list[str] = []
        self.run_sync_calls = 0

    async def execute(self, statement) -> None:
        self.executed.append(str(statement))

    async def run_sync(self, fn) -> None:
        self.run_sync_calls += 1


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self.dispose_calls = 0

    @asynccontextmanager
    async def begin(self):
        yield self._connection

    async def dispose(self) -> None:
        self.dispose_calls += 1


@pytest.mark.asyncio
async def test_init_db_does_not_create_schema_by_default(monkeypatch):
    """Startup init should not create tables unless explicitly enabled."""
    from src.database import session as db_session

    connection = _FakeConnection()
    monkeypatch.setattr(db_session, "engine", _FakeEngine(connection))
    monkeypatch.delenv("WENJIN_DB_AUTO_CREATE", raising=False)

    await db_session.init_db()

    assert connection.run_sync_calls == 0
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in stmt for stmt in connection.executed)


@pytest.mark.asyncio
async def test_init_db_can_opt_in_to_schema_creation(monkeypatch):
    """Metadata-based schema creation remains available for ephemeral environments."""
    from src.database import session as db_session

    connection = _FakeConnection()
    monkeypatch.setattr(db_session, "engine", _FakeEngine(connection))
    monkeypatch.setenv("WENJIN_DB_AUTO_CREATE", "true")

    await db_session.init_db()

    assert connection.run_sync_calls == 1


@pytest.mark.asyncio
async def test_reset_db_engine_rebuilds_process_local_engine(monkeypatch):
    """Engine/session proxies should follow a rebuilt process-local engine."""
    from src.database import session as db_session

    first_engine = _FakeEngine(_FakeConnection())
    second_engine = _FakeEngine(_FakeConnection())
    build_calls: list[object] = []

    monkeypatch.setattr(db_session, "_engine", first_engine)
    monkeypatch.setattr(db_session, "_session_factory", "first-session-factory")
    monkeypatch.setattr(db_session, "_build_engine", lambda: second_engine)

    def _fake_build_session_factory(target_engine):
        build_calls.append(target_engine)
        return "second-session-factory"

    monkeypatch.setattr(db_session, "_build_session_factory", _fake_build_session_factory)

    await db_session.reset_db_engine()

    assert build_calls == [second_engine]
    assert db_session.get_engine() is second_engine
    assert db_session.engine is not second_engine
    assert db_session.engine._connection is second_engine._connection
    assert db_session.get_async_session_factory() == "second-session-factory"
    assert first_engine.dispose_calls == 1
