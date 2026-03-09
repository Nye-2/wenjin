"""Tests for academic middlewares."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.middlewares.discipline_context import (
    DisciplineContextMiddleware,
    DisciplineRegistry,
)
from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware
from src.agents.thread_state import ThreadState


@pytest.fixture
def workspace_middleware():
    workspace_service = MagicMock()
    workspace_service.get = AsyncMock(return_value=MagicMock(
        id="ws-1",
        type="sci",
        discipline="computer_science",
        config={"style": "APA"},
    ))
    return WorkspaceContextMiddleware(workspace_service)


@pytest.mark.asyncio
async def test_workspace_context_injects_context(workspace_middleware):
    """Test WorkspaceContextMiddleware injects workspace context."""
    state = ThreadState(messages=[], workspace_id="ws-1")
    config = {"configurable": {}}

    result = await workspace_middleware.before_model(state, config)

    assert result["workspace_type"] == "sci"
    assert result["discipline"] == "computer_science"


@pytest.mark.asyncio
async def test_workspace_context_skips_without_workspace(workspace_middleware):
    """Test middleware skips when no workspace_id."""
    state = ThreadState(messages=[])
    config = {"configurable": {}}

    result = await workspace_middleware.before_model(state, config)

    assert result.get("workspace_type") is None


def test_discipline_registry_get_norms():
    """Test DisciplineRegistry returns correct norms."""
    registry = DisciplineRegistry()

    norms = registry.get_norms("computer_science", "sci")

    assert norms["citation_style"] == "IEEE"
    assert "Introduction" in norms["structure"]
    assert norms["writing_style"] == "technical and precise"


def test_discipline_registry_fallback():
    """Test DisciplineRegistry fallback for unknown discipline."""
    registry = DisciplineRegistry()

    # Should fallback to computer_science for unknown discipline
    norms = registry.get_norms("unknown_discipline")

    assert "citation_style" in norms
    assert "structure" in norms


@pytest.mark.asyncio
async def test_discipline_middleware_injects_norms():
    """Test DisciplineContextMiddleware injects discipline norms."""
    middleware = DisciplineContextMiddleware()

    state = ThreadState(
        messages=[],
        discipline="computer_science",
        workspace_type="sci",
    )
    config = {"configurable": {}}

    result = await middleware.before_model(state, config)

    assert "discipline_norms" in result
    assert result["discipline_norms"]["citation_style"] == "IEEE"
