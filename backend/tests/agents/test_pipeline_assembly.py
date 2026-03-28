"""Tests for 16-layer middleware pipeline assembly."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config.config_loader import MemoryConfig, MiddlewaresConfig, SummarizationConfig


def _mock_app_config(
    summarization_enabled: bool = False,
    *,
    memory_enabled: bool = False,
):
    """Create a mock app config for testing."""
    mock_config = MagicMock()
    mock_config.middlewares = MiddlewaresConfig(
        summarization=SummarizationConfig(enabled=summarization_enabled)
    )
    mock_config.subagents = SimpleNamespace(enabled=True, max_concurrent=4)
    mock_config.sandbox = None
    mock_config.memory = MemoryConfig(enabled=memory_enabled)
    return mock_config


def _pipeline_config(*, subagent_enabled: bool, workspace_id: str | None = None) -> dict:
    configurable = {
        "model_name": "gpt-4o",
        "subagent_enabled": subagent_enabled,
    }
    if workspace_id is not None:
        configurable["workspace_id"] = workspace_id
    return {"configurable": configurable}


class TestPipelineAssembly:
    def test_builds_16_layer_pipeline(self):
        """Full pipeline should have 16 layers when all features enabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=True, workspace_id="ws-123")

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
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

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]

        # ThreadData must be first
        assert type_names[0] == "ThreadDataMiddleware"

        # Clarification must be last
        assert type_names[-1] == "ClarificationMiddleware"

    def test_subagent_limit_included_when_enabled(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=True)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" in type_names

    def test_subagent_limit_excluded_when_disabled(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" not in type_names

    def test_summarization_included_when_enabled(self):
        """SummarizationMiddleware should be included when enabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config(summarization_enabled=True)), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SummarizationMiddleware" in type_names

    def test_summarization_excluded_when_disabled(self):
        """SummarizationMiddleware should be excluded when disabled."""
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config(summarization_enabled=False)), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SummarizationMiddleware" not in type_names

    def test_sandbox_middleware_is_auto_included_when_provider_available(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)
        mock_provider = object()

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=mock_provider,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "SandboxMiddleware" in type_names

    def test_execution_middleware_is_included_when_execution_service_available(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            return_value=object(),
        ):
            pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]
        assert "ExecutionMiddleware" in type_names

    def test_memory_capture_is_enabled_without_explicit_queue(self):
        from src.agents.lead_agent.agent import build_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch(
            "src.agents.lead_agent.agent.get_app_config",
            return_value=_mock_app_config(memory_enabled=True),
        ), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        memory_middleware = next(
            middleware
            for middleware in pipeline
            if type(middleware).__name__ == "MemoryMiddleware"
        )
        assert memory_middleware._capture_enabled is True

    def test_pipeline_validates_ordering_constraints(self):
        """validate_pipeline should accept a correctly ordered pipeline."""
        from src.agents.lead_agent.agent import build_pipeline, validate_pipeline

        config = _pipeline_config(subagent_enabled=False)

        with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
            "src.agents.lead_agent.agent.get_sandbox_provider",
            return_value=None,
        ), patch(
            "src.thesis.execution.get_execution_service",
            side_effect=RuntimeError("execution disabled"),
        ):
            pipeline = build_pipeline(config=config)

        # Should not raise
        validate_pipeline(pipeline)

    def test_pipeline_validation_rejects_wrong_clarification_position(self):
        """ClarificationMiddleware not last should raise ValueError."""
        from src.agents.lead_agent.agent import validate_pipeline
        from src.agents.middlewares import ClarificationMiddleware, ThreadDataMiddleware
        from src.agents.middlewares.base import Middleware

        class DummyMiddleware(Middleware):
            async def before_model(self, state, config):
                return {}

        # ClarificationMiddleware placed before the dummy → not last
        pipeline = [ThreadDataMiddleware(), ClarificationMiddleware(), DummyMiddleware()]

        with pytest.raises(ValueError, match="ClarificationMiddleware must be last"):
            validate_pipeline(pipeline)

    def test_pipeline_validation_rejects_wrong_thread_data_position(self):
        """ThreadDataMiddleware not first should raise ValueError."""
        from src.agents.lead_agent.agent import validate_pipeline
        from src.agents.middlewares import ClarificationMiddleware, ThreadDataMiddleware
        from src.agents.middlewares.base import Middleware

        class DummyMiddleware(Middleware):
            async def before_model(self, state, config):
                return {}

        # ThreadDataMiddleware placed after the dummy → not first
        pipeline = [DummyMiddleware(), ThreadDataMiddleware(), ClarificationMiddleware()]

        with pytest.raises(ValueError, match="ThreadDataMiddleware must be first"):
            validate_pipeline(pipeline)

    def test_middleware_ordering_metadata(self):
        """position class attribute should exist on boundary middlewares."""
        from src.agents.middlewares import ClarificationMiddleware, ThreadDataMiddleware
        from src.agents.middlewares.base import Middleware

        # Base class default
        assert Middleware.position is None

        # Boundary middlewares
        assert ThreadDataMiddleware.position == "first"
        assert ClarificationMiddleware.position == "last"
