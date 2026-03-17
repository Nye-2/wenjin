"""Tests for ThesisLeadAgent routing."""

import pytest
from unittest.mock import AsyncMock, patch

from src.agents.thesis_lead_agent import (
    THESIS_FEATURE_IDS,
    _build_system_prompt,
    execute_thesis_feature_graph,
    _FEATURE_GRAPH_REGISTRY,
)


class TestBuildSystemPrompt:
    def test_basic_prompt(self):
        result = _build_system_prompt("我的论文", None, None)
        assert "我的论文" in result
        assert "THESIS" in result

    def test_with_discipline(self):
        result = _build_system_prompt("论文", "计算机科学", None)
        assert "计算机科学" in result

    def test_with_memory(self):
        result = _build_system_prompt("论文", None, "<academic_memory>\n偏好APA\n</academic_memory>")
        assert "academic_memory" in result


class TestFeatureRouting:
    def test_all_feature_ids_defined(self):
        assert len(THESIS_FEATURE_IDS) == 6
        assert "deep_research" in THESIS_FEATURE_IDS
        assert "compile_export" in THESIS_FEATURE_IDS

    async def test_raises_for_unknown_feature(self):
        with pytest.raises(ValueError, match="No LangGraph sub-graph"):
            await execute_thesis_feature_graph(
                "nonexistent",
                {"workspace_id": "w1"},
            )

    async def test_routes_to_registered_graph(self):
        mock_fn = AsyncMock(return_value={"success": True})
        _FEATURE_GRAPH_REGISTRY["_test_feature"] = mock_fn
        try:
            result = await execute_thesis_feature_graph(
                "_test_feature",
                {"workspace_id": "w1", "workspace_name": "test"},
            )
            assert result["success"] is True
            mock_fn.assert_called_once()
        finally:
            _FEATURE_GRAPH_REGISTRY.pop("_test_feature", None)
