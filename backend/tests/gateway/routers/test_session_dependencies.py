"""Regression tests for shared DB dependency wiring."""

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
async def test_gateway_get_db_supports_async_context_manager(monkeypatch):
    """gateway deps core.get_db should consume get_db_session() as a context manager."""
    from src.gateway.deps import core

    session = AsyncMock()
    monkeypatch.setattr(
        core,
        "get_db_session",
        lambda: _DummySessionContext(session),
    )

    dependency_gen = core.get_db()
    yielded = await anext(dependency_gen)
    assert yielded is session
    await dependency_gen.aclose()
