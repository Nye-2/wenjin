"""Regression tests for router session dependency wiring."""

from unittest.mock import AsyncMock

import pytest


class _DummySessionContext:
    """Async context manager wrapper used to emulate get_db_session()."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_papers_get_session_supports_async_context_manager(monkeypatch):
    """papers.get_session should consume get_db_session() as a context manager."""
    from src.gateway.routers import papers

    session = AsyncMock()
    monkeypatch.setattr(
        papers,
        "get_db_session",
        lambda: _DummySessionContext(session),
    )

    dependency_gen = papers.get_session()
    yielded = await anext(dependency_gen)
    assert yielded is session
    await dependency_gen.aclose()


@pytest.mark.asyncio
async def test_artifacts_get_session_supports_async_context_manager(monkeypatch):
    """artifacts.get_session should consume get_db_session() as a context manager."""
    from src.gateway.routers import artifacts

    session = AsyncMock()
    monkeypatch.setattr(
        artifacts,
        "get_db_session",
        lambda: _DummySessionContext(session),
    )

    dependency_gen = artifacts.get_session()
    yielded = await anext(dependency_gen)
    assert yielded is session
    await dependency_gen.aclose()
