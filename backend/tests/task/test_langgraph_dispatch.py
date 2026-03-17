"""Tests for LangGraph dispatch integration in workspace_feature_handler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import (
    _ensure_graphs_loaded,
    _schedule_memory_extraction,
    _try_langgraph_execution,
)


@pytest.fixture
def progress():
    """Create a mock ProgressTracker."""
    tracker = AsyncMock()
    tracker.update = AsyncMock()
    return tracker


@pytest.fixture(autouse=True)
def reset_graphs_loaded():
    """Reset _GRAPHS_LOADED flag before each test."""
    import src.task.handlers.workspace_feature_handler as mod
    original = mod._GRAPHS_LOADED
    mod._GRAPHS_LOADED = False
    yield
    mod._GRAPHS_LOADED = original


# ── Test 1: Import failure returns None ──


@pytest.mark.asyncio
async def test_try_langgraph_returns_none_when_no_registry(progress):
    """When thesis_lead_agent cannot be imported, return None (fallback)."""
    with patch(
        "src.task.handlers.workspace_feature_handler._ensure_graphs_loaded"
    ):
        with patch.dict("sys.modules", {"src.agents.thesis_lead_agent": None}):
            result = await _try_langgraph_execution(
                "literature_management",
                {"workspace_type": "thesis", "feature_id": "literature_management"},
                progress,
            )
    assert result is None


# ── Test 2: Unregistered feature returns None ──


@pytest.mark.asyncio
async def test_try_langgraph_returns_none_for_unregistered_feature(progress):
    """When feature_id is not in the registry, return None."""
    mock_module = MagicMock()
    mock_module._FEATURE_GRAPH_REGISTRY = {}
    mock_module.execute_thesis_feature_graph = AsyncMock()

    with patch(
        "src.task.handlers.workspace_feature_handler._ensure_graphs_loaded"
    ):
        with patch.dict("sys.modules", {"src.agents.thesis_lead_agent": mock_module}):
            result = await _try_langgraph_execution(
                "nonexistent_feature",
                {"workspace_type": "thesis", "feature_id": "nonexistent_feature"},
                progress,
            )
    assert result is None
    mock_module.execute_thesis_feature_graph.assert_not_called()


# ── Test 3: Successful graph execution wraps result ──


@pytest.mark.asyncio
async def test_try_langgraph_wraps_result_on_success(progress):
    """On success, _try_langgraph_execution wraps the graph result."""
    graph_result = {
        "generation_mode": "llm",
        "content": "some generated content",
    }
    mock_execute = AsyncMock(return_value=graph_result)
    mock_registry = {"literature_management": mock_execute}

    mock_module = MagicMock()
    mock_module._FEATURE_GRAPH_REGISTRY = mock_registry
    mock_module.execute_thesis_feature_graph = mock_execute

    payload = {
        "workspace_type": "thesis",
        "feature_id": "literature_management",
        "feature_name": "文献管理",
        "handler_key": "thesis.literature_management",
        "user_id": "user-123",
    }

    with patch(
        "src.task.handlers.workspace_feature_handler._ensure_graphs_loaded"
    ):
        with patch.dict("sys.modules", {"src.agents.thesis_lead_agent": mock_module}):
            result = await _try_langgraph_execution(
                "literature_management", payload, progress
            )

    assert result is not None
    assert result["feature_id"] == "literature_management"
    assert result["workspace_type"] == "thesis"
    assert result["data"] == graph_result
    assert result["generation_mode"] == "llm"
    assert "LangGraph" in result["message"]
    assert result["refresh_targets"] == ["artifacts"]

    mock_execute.assert_awaited_once_with(
        "literature_management", payload, user_id="user-123"
    )
    # Should have called progress.update at least twice (start + done)
    assert progress.update.await_count >= 2


# ── Test 4: Exception in graph returns None (fallback) ──


@pytest.mark.asyncio
async def test_try_langgraph_returns_none_on_exception(progress):
    """When the graph raises, return None so the handler falls back."""
    mock_execute = AsyncMock(side_effect=RuntimeError("graph crashed"))
    mock_registry = {"literature_management": mock_execute}

    mock_module = MagicMock()
    mock_module._FEATURE_GRAPH_REGISTRY = mock_registry
    mock_module.execute_thesis_feature_graph = mock_execute

    payload = {
        "workspace_type": "thesis",
        "feature_id": "literature_management",
        "user_id": "user-123",
    }

    with patch(
        "src.task.handlers.workspace_feature_handler._ensure_graphs_loaded"
    ):
        with patch.dict("sys.modules", {"src.agents.thesis_lead_agent": mock_module}):
            result = await _try_langgraph_execution(
                "literature_management", payload, progress
            )

    assert result is None


# ── Test 5: Memory extraction no-ops without user_id ──


def test_schedule_memory_extraction_no_user_id():
    """_schedule_memory_extraction should be a no-op when no user_id in payload."""
    payload = {"feature_id": "literature_management"}
    result = {"message": "done"}
    # Should not raise
    _schedule_memory_extraction(payload, result)


# ── Test 6: _ensure_graphs_loaded is idempotent ──


def test_ensure_graphs_loaded_idempotent():
    """Calling _ensure_graphs_loaded twice should not raise."""
    import src.task.handlers.workspace_feature_handler as mod

    mod._GRAPHS_LOADED = False

    with patch(
        "src.task.handlers.workspace_feature_handler.logger"
    ):
        # First call: imports may fail, but should not raise
        try:
            _ensure_graphs_loaded()
        except ImportError:
            pass

        first_state = mod._GRAPHS_LOADED
        assert first_state is True

        # Second call: should be a no-op (already loaded)
        _ensure_graphs_loaded()
        assert mod._GRAPHS_LOADED is True
