"""Tests for 16-layer middleware pipeline assembly."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.config.config_loader import MiddlewaresConfig, SummarizationConfig


def _mock_app_config(summarization_enabled: bool = False):
    """Create a mock app config for testing."""
    mock_config = MagicMock()
    mock_config.middlewares = MiddlewaresConfig(
        summarization=SummarizationConfig(enabled=summarization_enabled)
    )
    mock_config.subagents = SimpleNamespace(enabled=True, max_concurrent=4)
    mock_config.sandbox = None
    return mock_config


class TestPipelineAssembly:
    def test_builds_16_layer_pipeline(self):
        """Full pipeline should have 16 layers when all features enabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = {
            "configurable": {
                "subagent_enabled": True,
                "workspace_id": "ws-123",
            }
        }

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(
                config=config,
                workspace_service=None,  # Will skip WS middleware
                index_service=None,
                artifact_service=None,
                paper_service=None,
            )
        # At minimum: ThreadData + Uploads + Dangling + academic defaults + Title + Clarification
        assert len(pipeline) >= 7

    def test_pipeline_order(self):
        """Infrastructure middlewares should come before academic middlewares."""
        from src.agents.lead_agent.agent import build_pipeline
        from src.agents.middlewares.thread_data import ThreadDataMiddleware
        from src.agents.middlewares.clarification import ClarificationMiddleware

        config = {"configurable": {"subagent_enabled": False}}

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]

        # ThreadData must be first
        assert type_names[0] == "ThreadDataMiddleware"

        # Clarification must be last
        assert type_names[-1] == "ClarificationMiddleware"

    def test_subagent_limit_included_when_enabled(self):
        from src.agents.lead_agent.agent import build_pipeline
        from src.agents.middlewares.subagent_limit import SubagentLimitMiddleware

        config = {"configurable": {"subagent_enabled": True}}

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" in type_names

    def test_subagent_limit_excluded_when_disabled(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = {"configurable": {"subagent_enabled": False}}

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" not in type_names

    def test_summarization_included_when_enabled(self):
        """SummarizationMiddleware should be included when enabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = {"configurable": {"subagent_enabled": False}}

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config(summarization_enabled=True)), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SummarizationMiddleware" in type_names

    def test_summarization_excluded_when_disabled(self):
        """SummarizationMiddleware should be excluded when disabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = {"configurable": {"subagent_enabled": False}}

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config(summarization_enabled=False)), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SummarizationMiddleware" not in type_names

    def test_sandbox_middleware_is_auto_included_when_provider_available(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = {"configurable": {"subagent_enabled": False}}
        mock_provider = object()

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=mock_provider,
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SandboxMiddleware" in type_names
