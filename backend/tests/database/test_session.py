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

    @asynccontextmanager
    async def begin(self):
        yield self._connection


@pytest.mark.asyncio
async def test_init_db_does_not_create_schema_by_default(monkeypatch):
    """Startup init should not create tables unless explicitly enabled."""
    from src.database import session as db_session

    connection = _FakeConnection()
    monkeypatch.setattr(db_session, "engine", _FakeEngine(connection))
    monkeypatch.delenv("ACADEMIAGPT_DB_AUTO_CREATE", raising=False)

    await db_session.init_db()

    assert connection.run_sync_calls == 0
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in stmt for stmt in connection.executed)


@pytest.mark.asyncio
async def test_init_db_can_opt_in_to_schema_creation(monkeypatch):
    """Metadata-based schema creation remains available for ephemeral environments."""
    from src.database import session as db_session

    connection = _FakeConnection()
    monkeypatch.setattr(db_session, "engine", _FakeEngine(connection))
    monkeypatch.setenv("ACADEMIAGPT_DB_AUTO_CREATE", "true")

    await db_session.init_db()

    assert connection.run_sync_calls == 1
