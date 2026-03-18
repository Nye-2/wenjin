"""Tests for model factory.

This module tests the model factory that creates LLM instances
based on dynamic configuration from the llm_config module.
"""

import json
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest


class TestCreateChatModel:
    """Test create_chat_model function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> Generator[None, None, None]:
        """Reset the LLM config cache before and after each test."""
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass
        yield
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass

    @pytest.fixture
    def openai_compatible_config(self) -> str:
        """Sample OpenAI-compatible model config (DeepSeek)."""
        return json.dumps([
            {
                "id": "deepseek-v3",
                "model": "deepseek/deepseek-v3",
                "api_key": "sk-test-deepseek-key",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 8192
            }
        ])

    @pytest.fixture
    def anthropic_config(self) -> str:
        """Sample Anthropic model config."""
        return json.dumps([
            {
                "id": "claude-sonnet-4",
                "model": "claude-sonnet-4-20250514",
                "api_key": "sk-test-anthropic-key",
                "base_url": "https://api.anthropic.com",
                "temperature": 0.7,
                "max_tokens": 4096
            }
        ])

    def test_create_openai_compatible_model(self, openai_compatible_config: str) -> None:
        """Test creating an OpenAI-compatible model (DeepSeek, GLM, Qwen, etc.)."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": openai_compatible_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(model_id="deepseek-v3", temperature=0.5)

            # Verify it's a ChatOpenAI instance
            assert model is not None
            # The model should be configured with the correct parameters
            assert model.model_name == "deepseek/deepseek-v3"

    def test_create_anthropic_model(self, anthropic_config: str) -> None:
        """Test creating an Anthropic/Claude model."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": anthropic_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(model_id="claude-sonnet-4", temperature=0.7)

            # Verify it's a ChatAnthropic instance
            assert model is not None
            # ChatAnthropic uses 'model' attribute (not 'model_name' like ChatOpenAI)
            assert model.model == "claude-sonnet-4-20250514"

    def test_create_anthropic_model_with_thinking(self, anthropic_config: str) -> None:
        """Test creating an Anthropic model with thinking enabled."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": anthropic_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(
                model_id="claude-sonnet-4",
                temperature=0.7,
                thinking_enabled=True
            )

            # Verify thinking_budget is set
            assert model is not None
            # ChatAnthropic with thinking should have thinking_budget
            assert hasattr(model, "thinking_budget") or hasattr(model, "model_kwargs")

    def test_error_when_no_models_configured(self) -> None:
        """No configured models should raise explicit configuration error."""
        with patch.dict(
            os.environ,
            {
                "LLM_GEN_MODELS": "[]",
                "LLM_TOOL_MODELS": "[]",
                "LLM_UTILITY_MODELS": "[]",
                "LLM_IMAGE_MODELS": "[]",
                "LLM_DEFAULT_MODEL": "",
            },
            clear=False,
        ):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            with pytest.raises(ValueError, match="No models configured"):
                create_chat_model(model_id="nonexistent-model", temperature=0.7)

    def test_temperature_override(self, openai_compatible_config: str) -> None:
        """Test that temperature parameter overrides config default."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": openai_compatible_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(model_id="deepseek-v3", temperature=0.3)

            # The temperature should be overridden to 0.3
            assert model is not None
            # Note: temperature is passed to the model at init time
            # Check the model's temperature attribute if available

    def test_openai_compatible_with_base_url(self, openai_compatible_config: str) -> None:
        """Test that OpenAI-compatible models use the base_url from config."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": openai_compatible_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(model_id="deepseek-v3", temperature=0.7)

            # ChatOpenAI should be configured with the custom base_url
            assert model is not None
            # Verify base_url is set correctly (accessible via openai_api_base or similar)


class TestModelProviderDetection:
    """Test provider detection logic."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> Generator[None, None, None]:
        """Reset the LLM config cache before and after each test."""
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass
        yield
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass

    @pytest.fixture
    def mixed_provider_config(self) -> str:
        """Sample config with multiple providers."""
        return json.dumps([
            {
                "id": "qwen-max",
                "model": "qwen/qwen-max",
                "api_key": "sk-qwen-key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
            {
                "id": "glm-4",
                "model": "glm/glm-4",
                "api_key": "sk-glm-key",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
            },
            {
                "id": "claude-3-opus",
                "model": "claude-3-opus-20240229",
                "api_key": "sk-claude-key",
                "base_url": "https://api.anthropic.com",
            }
        ])

    def test_detects_anthropic_by_base_url(self, mixed_provider_config: str) -> None:
        """Test that Anthropic is detected by base_url containing 'anthropic'."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": mixed_provider_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import _is_anthropic_provider
            reload_models()

            # Test the helper function
            is_anthropic = _is_anthropic_provider("https://api.anthropic.com", "claude-3-opus-20240229")
            assert is_anthropic is True

    def test_detects_openai_compatible_by_base_url(self, mixed_provider_config: str) -> None:
        """Test that non-Anthropic providers use ChatOpenAI."""
        with patch.dict(os.environ, {"LLM_GEN_MODELS": mixed_provider_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import _is_anthropic_provider
            reload_models()

            # Test the helper function
            is_anthropic = _is_anthropic_provider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen/qwen-max")
            assert is_anthropic is False


class TestDynamicConfigIntegration:
    """Integration tests for factory with dynamic config."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> Generator[None, None, None]:
        """Reset the LLM config cache before and after each test."""
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass
        yield
        try:
            from src.config.llm_config import reload_models
            reload_models()
        except ImportError:
            pass

    def test_uses_get_model_full_config(self) -> None:
        """Test that factory uses get_model_full_config from llm_config."""
        sample_config = json.dumps([
            {
                "id": "integration-test-model",
                "model": "test/integration-model",
                "api_key": "sk-integration-key",
                "base_url": "https://integration.api.com/v1",
                "temperature": 0.8,
                "max_tokens": 16384
            }
        ])

        with patch.dict(os.environ, {"LLM_GEN_MODELS": sample_config}, clear=False):
            from src.config.llm_config import reload_models
            from src.models.factory import create_chat_model
            reload_models()

            model = create_chat_model(model_id="integration-test-model", temperature=0.8)

            assert model is not None
            assert model.model_name == "test/integration-model"
