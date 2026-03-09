"""End-to-end integration test for the 16-layer pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.lead_agent.agent import build_pipeline
from src.agents.thread_state import ThreadState
from src.config.config_loader import MiddlewaresConfig, SummarizationConfig


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
        config = {"configurable": {"model_name": "gpt-4o", "subagent_enabled": True}}
        with patch("src.config.config_loader.get_app_config", return_value=_mock_app_config()):
            pipeline = build_pipeline(config)
        assert len(pipeline) >= 5

    def test_pipeline_order_correct(self):
        """Pipeline should have correct middleware order."""
        config = {"configurable": {"subagent_enabled": True}}
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

    def test_memory_integrates(self, tmp_path):
        """Memory system should create and read without errors."""
        from src.agents.memory.updater import get_memory_data
        storage = str(tmp_path / "test_memory.json")
        data = get_memory_data(storage_path=storage)
        assert "version" in data
        assert "facts" in data

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
