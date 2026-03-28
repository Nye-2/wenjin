"""Context-loading middlewares must degrade gracefully on timeout."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.middlewares.knowledge_context import KnowledgeContextMiddleware
from src.agents.middlewares.literature_context import LiteratureContextMiddleware
from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware


async def _slow_coro(*args, **kwargs):
    """Simulates a service call that never finishes."""
    await asyncio.sleep(60)
    return "should not reach here"


@pytest.mark.asyncio
async def test_workspace_context_timeout_returns_empty():
    """WorkspaceContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.get.side_effect = _slow_coro

    mw = WorkspaceContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert result == {}


@pytest.mark.asyncio
async def test_literature_context_timeout_returns_empty():
    """LiteratureContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.get_workspace_toc_summary.side_effect = _slow_coro

    mw = LiteratureContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert result == {}


@pytest.mark.asyncio
async def test_knowledge_context_timeout_returns_empty():
    """KnowledgeContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.list_by_workspace.side_effect = _slow_coro

    mw = KnowledgeContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert result == {}


@pytest.mark.asyncio
async def test_memory_context_timeout_returns_empty():
    """MemoryMiddleware must return {} on build_memory_context timeout."""
    from src.agents.middlewares.memory import MemoryMiddleware

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        side_effect=_slow_coro,
    ):
        mw = MemoryMiddleware(
            enabled=True,
            inject_enabled=True,
            timeout=0.05,
        )
        state = {"messages": [], "workspace_id": "ws-1"}
        config = {"configurable": {"user_id": "user-1", "workspace_id": "ws-1"}}

        result = await mw.before_model(state, config)
        assert result == {}
