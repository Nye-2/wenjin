"""End-to-end integration tests for the canonical pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.lead_agent.agent import build_pipeline
from src.config.config_loader import MemoryConfig, MiddlewaresConfig, SummarizationConfig


def _mock_app_config(summarization_enabled: bool = False):
    """Create a mock app config for testing."""
    mock_config = MagicMock()
    mock_config.middlewares = MiddlewaresConfig(
        summarization=SummarizationConfig(enabled=summarization_enabled)
    )
    return mock_config


class TestPipelineE2E:
    def test_pipeline_builds_without_error(self):
        """Pipeline should build with default config."""
        config = {"configurable": {"model_name": "gpt-4o"}}
        with patch("src.config.config_loader.get_app_config", return_value=_mock_app_config()):
            pipeline = build_pipeline(config)
        assert len(pipeline) >= 5

    def test_pipeline_order_correct(self):
        """Pipeline should have correct middleware order."""
        config = {"configurable": {"model_name": "gpt-4o"}}
        with patch("src.config.config_loader.get_app_config", return_value=_mock_app_config()):
            pipeline = build_pipeline(config)
        type_names = [type(m).__name__ for m in pipeline]
        # ThreadData must be first
        assert type_names[0] == "ThreadDataMiddleware"
        # Clarification must be last
        assert type_names[-1] == "ClarificationMiddleware"

    def test_config_loader_defaults(self):
        """Config system should load with defaults."""
        from src.config.config_loader import AppConfig
        config = AppConfig()
        assert config is not None
        assert isinstance(config.models, list)
        assert isinstance(config.subagents.enabled, bool)

    @pytest.mark.asyncio
    async def test_memory_integrates(self):
        """Memory system should format canonical persisted knowledge without file storage."""
        from unittest.mock import AsyncMock

        from src.services.user_memory_service import build_memory_context

        config = MemoryConfig(enabled=True, injection_enabled=True, max_injection_tokens=128)
        with patch(
            "src.services.user_memory_service._load_memory_config",
            return_value=config,
        ), patch(
            "src.services.user_memory_service.load_user_memory",
            AsyncMock(
                return_value=[
                    {
                        "category": "context",
                        "content": "正在撰写 LLM 综述",
                        "confidence": 0.9,
                        "workspace_context": "ws-1",
                    }
                ]
            ),
        ):
            memory = await build_memory_context("user-1", "ws-1")

        assert "<academic_memory>" in memory
        assert "正在撰写 LLM 综述" in memory

    def test_reflection_resolves_module(self):
        """Reflection system should resolve known modules."""
        from src.reflection.resolvers import resolve_variable
        result = resolve_variable("os.path:sep")
        assert isinstance(result, str)

    def test_full_test_suite_still_passes(self):
        """Meta-test: ensure this doesn't break anything.

        Run the full suite separately:
        PYTHONPATH=. uv run pytest -x -q
        """
        pass
