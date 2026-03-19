"""Tests for ThesisLeadAgent routing via WorkspaceLeadAgent."""

import sys
from unittest.mock import AsyncMock

import pytest

from src.agents.workspace_lead_agent import (
    _FEATURE_GRAPH_REGISTRY,
    _LOADED_WORKSPACES,
    THESIS_FEATURE_IDS,
    _build_system_prompt,
    _ensure_graphs_loaded,
    execute_thesis_feature_graph,
)


class TestBuildSystemPrompt:
    def test_basic_prompt(self):
        result = _build_system_prompt("我的论文", "thesis", None, None)
        assert "我的论文" in result
        assert "THESIS" in result

    def test_with_discipline(self):
        result = _build_system_prompt("论文", "thesis", "计算机科学", None)
        assert "计算机科学" in result

    def test_with_memory(self):
        result = _build_system_prompt("论文", "thesis", None, "<academic_memory>\n偏好APA\n</academic_memory>")
        assert "academic_memory" in result


class TestFeatureRouting:
    def test_all_feature_ids_defined(self):
        assert len(THESIS_FEATURE_IDS) == 6
        assert "deep_research" in THESIS_FEATURE_IDS
        assert "compile_export" in THESIS_FEATURE_IDS

    @pytest.mark.asyncio
    async def test_raises_for_unknown_feature(self):
        with pytest.raises(ValueError, match="No LangGraph sub-graph"):
            await execute_thesis_feature_graph(
                "nonexistent",
                {"workspace_id": "w1"},
            )

    @pytest.mark.asyncio
    async def test_routes_to_registered_graph(self):
        mock_fn = AsyncMock(return_value={"success": True})
        _FEATURE_GRAPH_REGISTRY["thesis._test_feature"] = mock_fn
        try:
            result = await execute_thesis_feature_graph(
                "_test_feature",
                {"workspace_id": "w1", "workspace_name": "test"},
            )
            assert result["success"] is True
            mock_fn.assert_called_once()
        finally:
            _FEATURE_GRAPH_REGISTRY.pop("thesis._test_feature", None)

    def test_thesis_graph_modules_register_feature_handlers(self):
        module_names = [
            "src.agents.graphs.thesis",
            "src.agents.graphs.thesis.deep_research",
            "src.agents.graphs.thesis.literature_management",
            "src.agents.graphs.thesis.opening_research",
            "src.agents.graphs.thesis.thesis_writing",
            "src.agents.graphs.thesis.figure_generation",
            "src.agents.graphs.thesis.compile_export",
        ]
        expected_keys = {
            "thesis.deep_research",
            "thesis.literature_management",
            "thesis.opening_research",
            "thesis.thesis_writing",
            "thesis.figure_generation",
            "thesis.compile_export",
        }

        previous_registry = dict(_FEATURE_GRAPH_REGISTRY)
        previous_loaded = set(_LOADED_WORKSPACES)
        previous_modules = {name: sys.modules.get(name) for name in module_names}

        try:
            for name in module_names:
                sys.modules.pop(name, None)
            _FEATURE_GRAPH_REGISTRY.clear()
            _LOADED_WORKSPACES.clear()

            _ensure_graphs_loaded("thesis")

            assert expected_keys.issubset(set(_FEATURE_GRAPH_REGISTRY.keys()))
        finally:
            _FEATURE_GRAPH_REGISTRY.clear()
            _FEATURE_GRAPH_REGISTRY.update(previous_registry)
            _LOADED_WORKSPACES.clear()
            _LOADED_WORKSPACES.update(previous_loaded)
            for name, module in previous_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
