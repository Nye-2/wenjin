"""Tests for LLM configuration loader.

This module tests the LLM configuration loader that parses model configs
from environment variables (LLM_MODELS, LLM_IMAGE_MODELS).
"""

import json
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest

# We'll import from the module we're about to create
# This will fail initially (TDD red phase)


class TestLLMConfigParsing:
    """Test parsing models from environment variables."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> Generator[None, None, None]:
        """Reset the LLM config cache before and after each test."""
        # Import here to avoid import errors before module exists
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
    def sample_llm_models(self) -> str:
        """Sample LLM models JSON string."""
        return json.dumps([
            {
                "id": "deepseek-v3",
                "model": "deepseek/deepseek-v3",
                "api_key": "sk-test-gen-123",
                "base_url": "https://api.deepseek.com"
            },
            {
                "id": "gpt-4",
                "model": "openai/gpt-4-turbo",
                "api_key": "sk-test-openai-456",
                "base_url": "https://api.openai.com/v1"
            }
        ])

    @pytest.fixture
    def sample_image_models(self) -> str:
        """Sample image models JSON string."""
        return json.dumps([
            {
                "id": "kling-v2",
                "model": "kling-v2",
                "api_key": "sk-test-image-789",
                "base_url": "https://api.klingai.com/v1"
            }
        ])

    def test_get_llm_models_returns_parsed_models(self, sample_llm_models: str) -> None:
        """Test that get_llm_models returns models parsed from env."""
        with patch.dict(os.environ, {"LLM_MODELS": sample_llm_models}, clear=False):
            from src.config.llm_config import get_llm_models, reload_models
            reload_models()  # Clear cache to pick up new env

            models = get_llm_models()

            assert len(models) == 2
            model_ids = [m.id for m in models]
            assert "deepseek-v3" in model_ids
            assert "gpt-4" in model_ids

    def test_get_image_models_returns_parsed_models(self, sample_image_models: str) -> None:
        """Test that get_image_models returns models parsed from env."""
        with patch.dict(os.environ, {"LLM_IMAGE_MODELS": sample_image_models}, clear=False):
            from src.config.llm_config import get_image_models, reload_models
            reload_models()  # Clear cache to pick up new env

            models = get_image_models()

            assert len(models) == 1
            assert models[0].id == "kling-v2"

    def test_missing_required_field_raises_error(self) -> None:
        """Test that missing required fields raise an error."""
        invalid_models = json.dumps([
            {
                "id": "incomplete-model",
                "model": "test/model"
                # Missing api_key and base_url
            }
        ])

        with patch.dict(os.environ, {"LLM_MODELS": invalid_models}, clear=False):
            from src.config.llm_config import get_llm_models, reload_models
            reload_models()

            # Should log warning but return empty list (graceful handling)
            models = get_llm_models()
            assert len(models) == 0

    def test_invalid_json_logs_warning(self) -> None:
        """Test that invalid JSON is handled gracefully with logging."""
        invalid_json = "not a valid json["

        with patch.dict(os.environ, {"LLM_MODELS": invalid_json}, clear=False):
            from src.config.llm_config import get_llm_models, reload_models
            reload_models()

            # Should not raise, return empty list
            models = get_llm_models()
            assert models == []


class TestModelConfig:
    """Test ModelConfig Pydantic model."""

    def test_model_config_has_required_fields(self) -> None:
        """Test that ModelConfig has all required fields."""
        from src.config.llm_config import ModelConfig

        config = ModelConfig(
            id="test-model",
            model="test/model-string",
            api_key="sk-test-key",
            base_url="https://api.test.com"
        )

        assert config.id == "test-model"
        assert config.model == "test/model-string"
        assert config.api_key == "sk-test-key"
        assert config.base_url == "https://api.test.com"

    def test_model_config_optional_fields(self) -> None:
        """Test that ModelConfig supports optional fields."""
        from src.config.llm_config import ModelConfig

        config = ModelConfig(
            id="test-model",
            model="test/model-string",
            api_key="sk-test-key",
            base_url="https://api.test.com",
            temperature=0.5,
            max_tokens=8192
        )

        assert config.temperature == 0.5
        assert config.max_tokens == 8192


class TestGetModelConfig:
    """Test get_model_config and get_model_full_config functions."""

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
    def sample_models(self) -> str:
        """Sample models for testing."""
        return json.dumps([
            {
                "id": "test-llm",
                "model": "test/llm-model",
                "api_key": "sk-llm-key",
                "base_url": "https://llm.api.com",
                "temperature": 0.7,
                "max_tokens": 4096
            }
        ])

    def test_get_model_config_returns_model_info(self, sample_models: str) -> None:
        """Test that get_model_config returns model info."""
        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_model_config, reload_models
            reload_models()

            model = get_model_config("test-llm")

            assert model is not None
            assert model.id == "test-llm"
            assert model.model == "test/llm-model"

    def test_get_model_config_returns_none_for_unknown(self, sample_models: str) -> None:
        """Test that get_model_config returns None for unknown model."""
        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_model_config, reload_models
            reload_models()

            model = get_model_config("unknown-model")

            assert model is None

    def test_get_model_full_config_returns_complete_dict(self, sample_models: str) -> None:
        """Test that get_model_full_config returns complete configuration dict."""
        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_model_full_config, reload_models
            reload_models()

            full_config = get_model_full_config("test-llm")

            assert full_config is not None
            assert full_config["api_key"] == "sk-llm-key"
            assert full_config["base_url"] == "https://llm.api.com"
            assert full_config["model"] == "test/llm-model"
            assert full_config["temperature"] == 0.7
            assert full_config["max_tokens"] == 4096
            assert full_config["supports_thinking"] is False
            assert full_config["supports_vision"] is False
            assert full_config["supports_reasoning_effort"] is False

    def test_get_model_full_config_includes_capability_flags(self) -> None:
        sample_models = json.dumps([
            {
                "id": "capability-model",
                "model": "provider/capability-model",
                "api_key": "sk-cap",
                "base_url": "https://example.com/v1",
                "supports_thinking": True,
                "supports_vision": True,
                "supports_reasoning_effort": True,
            }
        ])
        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_model_full_config, reload_models

            reload_models()
            full_config = get_model_full_config("capability-model")

            assert full_config["supports_thinking"] is True
            assert full_config["supports_vision"] is True
            assert full_config["supports_reasoning_effort"] is True

    def test_get_model_full_config_raises_for_unknown(self, sample_models: str) -> None:
        """Test that get_model_full_config raises ValueError for unknown model."""
        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_model_full_config, reload_models
            reload_models()

            with pytest.raises(ValueError, match="Model not found"):
                get_model_full_config("unknown-model")


class TestCaching:
    """Test caching behavior."""

    def test_models_are_cached(self) -> None:
        """Test that models are cached and not re-parsed on each call."""
        sample_models = json.dumps([
            {
                "id": "cached-model",
                "model": "test/model",
                "api_key": "sk-key",
                "base_url": "https://api.test.com"
            }
        ])

        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_llm_models, get_model_config, reload_models
            reload_models()

            # First call to populate cache
            get_llm_models()

            # Second call should return same cached model instance
            model1 = get_model_config("cached-model")
            model2 = get_model_config("cached-model")

            # Model objects should be the same instance (cached)
            assert model1 is model2

    def test_reload_models_clears_cache(self) -> None:
        """Test that reload_models clears the cache."""
        sample_models = json.dumps([
            {
                "id": "reload-test",
                "model": "test/model",
                "api_key": "sk-key",
                "base_url": "https://api.test.com"
            }
        ])

        with patch.dict(os.environ, {"LLM_MODELS": sample_models}, clear=False):
            from src.config.llm_config import get_llm_models, reload_models

            reload_models()
            models1 = get_llm_models()

            # Update env
            new_sample = json.dumps([
                {
                    "id": "new-model",
                    "model": "test/new-model",
                    "api_key": "sk-key",
                    "base_url": "https://api.test.com"
                }
            ])
            with patch.dict(os.environ, {"LLM_MODELS": new_sample}, clear=False):
                reload_models()
                models2 = get_llm_models()

                assert len(models1) == 1
                assert models1[0].id == "reload-test"
                assert len(models2) == 1
                assert models2[0].id == "new-model"


class TestDefaultModelResolution:
    """Test default model resolution helpers."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> Generator[None, None, None]:
        from src.config.llm_config import reload_models

        reload_models()
        yield
        reload_models()

    def test_get_default_model_prefers_explicit_llm_default_model(self) -> None:
        llm_models = json.dumps([
            {
                "id": "llm-a",
                "model": "provider/llm-a",
                "api_key": "sk-llm",
                "base_url": "https://example.com/v1",
            }
        ])
        with patch.dict(
            os.environ,
            {
                "LLM_MODELS": llm_models,
                "LLM_DEFAULT_MODEL": "llm-a",
            },
            clear=False,
        ):
            from src.config.llm_config import get_default_model_id, reload_models

            reload_models()
            assert get_default_model_id() == "llm-a"

    def test_get_default_model_prefers_first_llm_model_when_env_not_set(self) -> None:
        llm_models = json.dumps([
            {
                "id": "llm-primary",
                "model": "provider/llm-primary",
                "api_key": "sk-llm",
                "base_url": "https://example.com/v1",
            }
        ])
        with patch.dict(
            os.environ,
            {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": ""},
            clear=False,
        ):
            from src.config.llm_config import get_default_model_id, reload_models

            reload_models()
            assert get_default_model_id() == "llm-primary"

    def test_get_default_model_raises_for_invalid_explicit_env(self) -> None:
        llm_models = json.dumps([
            {
                "id": "llm-primary",
                "model": "provider/llm-primary",
                "api_key": "sk-llm",
                "base_url": "https://example.com/v1",
            }
        ])
        with patch.dict(
            os.environ,
            {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "missing-model"},
            clear=False,
        ):
            from src.config.llm_config import get_default_model_id, reload_models

            reload_models()
            with pytest.raises(ValueError, match="LLM_DEFAULT_MODEL is not configured: missing-model"):
                get_default_model_id()

    def test_resolve_model_id_raises_for_unknown_requested_model(self) -> None:
        llm_models = json.dumps([
            {
                "id": "llm-default",
                "model": "provider/llm-default",
                "api_key": "sk-llm",
                "base_url": "https://example.com/v1",
            }
        ])
        with patch.dict(
            os.environ,
            {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "llm-default"},
            clear=False,
        ):
            from src.config.llm_config import reload_models, resolve_model_id

            reload_models()
            with pytest.raises(ValueError, match="Unknown model id: unknown-model"):
                resolve_model_id("unknown-model")
