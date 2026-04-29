"""Tests for thesis feature routing through the feature graph registry."""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.feature_leader.graph_registry import (
    _FEATURE_GRAPH_REGISTRY,
    _LOADED_WORKSPACES,
    THESIS_FEATURE_IDS,
    _build_system_prompt,
    _derive_feature_memory_context,
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
        assert len(THESIS_FEATURE_IDS) == 5
        assert "deep_research" in THESIS_FEATURE_IDS
        assert "figure_generation" in THESIS_FEATURE_IDS

    def test_derive_feature_memory_context_from_chat_params(self):
        context = _derive_feature_memory_context(
            {
                "params": {
                    "__thread_context_focus": "请围绕医学影像分割场景做调研",
                    "__leader_workflow_highlights": "发现热点方向：弱监督分割；证据缺口：跨机构泛化评估不足",
                    "topic": "多模态大模型",
                    "keywords": ["分割", "医学影像", "benchmark"],
                    "__thread_context_digest": "用户: ...",
                }
            }
        )

        assert context is not None
        assert "医学影像分割" in context
        assert "证据缺口" in context
        assert "多模态大模型" in context
        assert "benchmark" in context

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

    @pytest.mark.asyncio
    async def test_routes_with_contextual_memory_injection(self):
        captured_state = {}

        async def _mock_graph_fn(initial_state, payload):
            captured_state.update(initial_state)
            return {"success": True}

        _FEATURE_GRAPH_REGISTRY["thesis._test_feature"] = _mock_graph_fn
        try:
            with patch(
                "src.agents.feature_leader.graph_registry._ensure_graphs_loaded",
                return_value=None,
            ), patch(
                "src.services.user_memory_service.build_memory_context",
                new=AsyncMock(return_value="<academic_memory>偏好 IEEE</academic_memory>"),
            ) as build_memory_context:
                result = await execute_thesis_feature_graph(
                    "_test_feature",
                    {
                        "workspace_id": "w1",
                        "workspace_name": "test",
                        "params": {
                            "topic": "图神经网络",
                            "__thread_context_focus": "做一个综述",
                        },
                    },
                    user_id="user-1",
                )

            assert result["success"] is True
            build_memory_context.assert_awaited_once()
            assert captured_state["memory_context"] == "<academic_memory>偏好 IEEE</academic_memory>"
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
        ]
        expected_keys = {
            "thesis.deep_research",
            "thesis.literature_management",
            "thesis.opening_research",
            "thesis.thesis_writing",
            "thesis.figure_generation",
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
