"""LLM configuration loader for AcademiaGPT v2.

This module parses model configurations from environment variables
(LLM_GEN_MODELS, LLM_TOOL_MODELS, LLM_UTILITY_MODELS, LLM_IMAGE_MODELS)
and provides access functions.

Configuration format (.env file):
    LLM_GEN_MODELS=[{"id":"deepseek-v3","model":"deepseek/deepseek-v3","api_key":"sk-xxx","base_url":"https://api.deepseek.com"}]
    LLM_TOOL_MODELS=[{"id":"kimi-k2.5","model":"openai/moonshotai/kimi-k2.5","api_key":"sk-xxx","base_url":"https://api.moonshot.cn/v1"}]
    LLM_UTILITY_MODELS=[{"id":"qwen-flash","model":"qwen-flash","api_key":"sk-xxx","base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1"}]
    LLM_IMAGE_MODELS=[{"id":"kling-v2-1","model":"kling-v2-1","api_key":"sk-xxx","base_url":"https://api.klingai.com/v1"}]

Required fields: id, model, api_key, base_url
"""

import json
import logging
import os
import threading

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMSettings:
    """LLM global settings from environment."""

    TEMPERATURE: float = 0.7
    TIMEOUT: float = 120.0
    MAX_RETRIES: int = 3

    @classmethod
    def load(cls) -> None:
        """Load LLM settings from environment."""
        if temp := os.environ.get("LLM_TEMPERATURE"):
            try:
                cls.TEMPERATURE = float(temp)
            except ValueError:
                pass
        if timeout := os.environ.get("LLM_TIMEOUT"):
            try:
                cls.TIMEOUT = float(timeout)
            except ValueError:
                pass
        if retries := os.environ.get("LLM_MAX_RETRIES"):
            try:
                cls.MAX_RETRIES = int(retries)
            except ValueError:
                pass


class ModelConfig(BaseModel):
    """Model configuration with required and optional fields.

    Each model must have independent api_key and base_url.
    """

    # Required fields
    id: str = Field(..., description="Unique model identifier (used by frontend)")
    model: str = Field(..., description="Actual model string for API calls")
    api_key: str = Field(..., description="Model-specific API key")
    base_url: str = Field(..., description="Model-specific base URL")

    # Optional fields with defaults
    name: str = Field(default="", description="Display name")
    description: str = Field(default="", description="Model description", alias="desc")
    temperature: float = Field(default=0.7, description="Default temperature", alias="temp")
    max_tokens: int = Field(default=32768, description="Maximum output tokens")
    supports_streaming: bool = Field(default=True, description="Supports streaming output")
    supports_tools: bool = Field(default=False, description="Supports tool/function calling")
    supports_json_mode: bool = Field(default=True, description="Supports JSON response format")
    supports_json_schema: bool = Field(default=False, description="Supports JSON schema response format")

    class Config:
        populate_by_name = True


def _parse_model_from_json(data: dict) -> ModelConfig | None:
    """
    Parse a ModelConfig from JSON data.

    Args:
        data: Dictionary containing model configuration

    Returns:
        ModelConfig if parsing succeeds, None if required fields are missing
    """
    required_fields = ["id", "model", "api_key", "base_url"]
    missing = [f for f in required_fields if not data.get(f)]

    if missing:
        logger.warning("Model config missing required fields: %s. Skipping.", missing)
        return None

    try:
        return ModelConfig(
            id=data["id"],
            model=data["model"],
            api_key=data["api_key"],
            base_url=data["base_url"],
            name=data.get("name", data.get("id", "")),
            description=data.get("desc", data.get("description", "")),
            temperature=data.get("temp", data.get("temperature", 0.7)),
            max_tokens=data.get("max_tokens", 32768),
            supports_streaming=data.get("supports_streaming", True),
            supports_tools=data.get("supports_tools", False),
            supports_json_mode=data.get("supports_json_mode", True),
            supports_json_schema=data.get("supports_json_schema", False),
        )
    except Exception as e:
        logger.warning("Failed to parse model config: %s. Skipping.", e)
        return None


def _load_models_from_env() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Load models from environment variables.

    Returns:
        Tuple of (gen_models, tool_models, utility_models, image_models)
    """
    gen_models: dict[str, ModelConfig] = {}
    tool_models: dict[str, ModelConfig] = {}
    utility_models: dict[str, ModelConfig] = {}
    image_models: dict[str, ModelConfig] = {}

    # Load LLM global settings
    LLMSettings.load()

    # Parse generation models from LLM_GEN_MODELS
    gen_models_json = os.environ.get("LLM_GEN_MODELS", "")
    if gen_models_json:
        try:
            models_data = json.loads(gen_models_json)
            for m in models_data:
                model_config = _parse_model_from_json(m)
                if model_config:
                    gen_models[model_config.id] = model_config
            logger.info("Loaded %d generation models from LLM_GEN_MODELS", len(gen_models))
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM_GEN_MODELS JSON: %s", e)
    else:
        logger.debug("LLM_GEN_MODELS environment variable not set")

    # Parse tool models from LLM_TOOL_MODELS
    tool_models_json = os.environ.get("LLM_TOOL_MODELS", "")
    if tool_models_json:
        try:
            models_data = json.loads(tool_models_json)
            for m in models_data:
                model_config = _parse_model_from_json(m)
                if model_config:
                    tool_models[model_config.id] = model_config
            logger.info("Loaded %d tool models from LLM_TOOL_MODELS", len(tool_models))
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM_TOOL_MODELS JSON: %s", e)
    else:
        logger.debug("LLM_TOOL_MODELS environment variable not set")

    # Parse utility models from LLM_UTILITY_MODELS
    utility_models_json = os.environ.get("LLM_UTILITY_MODELS", "")
    if utility_models_json:
        try:
            models_data = json.loads(utility_models_json)
            for m in models_data:
                model_config = _parse_model_from_json(m)
                if model_config:
                    utility_models[model_config.id] = model_config
            logger.info("Loaded %d utility models from LLM_UTILITY_MODELS", len(utility_models))
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM_UTILITY_MODELS JSON: %s", e)
    else:
        logger.debug("LLM_UTILITY_MODELS environment variable not set")

    # Parse image models from LLM_IMAGE_MODELS
    image_models_json = os.environ.get("LLM_IMAGE_MODELS", "")
    if image_models_json:
        try:
            models_data = json.loads(image_models_json)
            for m in models_data:
                model_config = _parse_model_from_json(m)
                if model_config:
                    image_models[model_config.id] = model_config
            logger.info("Loaded %d image models from LLM_IMAGE_MODELS", len(image_models))
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM_IMAGE_MODELS JSON: %s", e)
    else:
        logger.debug("LLM_IMAGE_MODELS environment variable not set")

    return gen_models, tool_models, utility_models, image_models


# Global cache with thread-safe access
_CACHED_GEN_MODELS: dict[str, ModelConfig] | None = None
_CACHED_TOOL_MODELS: dict[str, ModelConfig] | None = None
_CACHED_UTILITY_MODELS: dict[str, ModelConfig] | None = None
_CACHED_IMAGE_MODELS: dict[str, ModelConfig] | None = None
_cache_lock = threading.Lock()


def _get_cached_models() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Get cached model configurations (lazy loading, thread-safe).

    Returns:
        Tuple of (gen_models, tool_models, utility_models, image_models)
    """
    global _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS, _CACHED_UTILITY_MODELS, _CACHED_IMAGE_MODELS

    if _CACHED_GEN_MODELS is None:
        with _cache_lock:
            # Double-check after acquiring lock
            if _CACHED_GEN_MODELS is None:
                _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS, _CACHED_UTILITY_MODELS, _CACHED_IMAGE_MODELS = _load_models_from_env()

    return _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS, _CACHED_UTILITY_MODELS, _CACHED_IMAGE_MODELS


def reload_models() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Reload model configurations from environment variables.

    This clears the cache and reloads models, useful for hot-reloading
    configuration changes without restarting the application.

    Returns:
        Tuple of (gen_models, tool_models, utility_models, image_models)
    """
    global _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS, _CACHED_UTILITY_MODELS, _CACHED_IMAGE_MODELS

    with _cache_lock:
        _CACHED_GEN_MODELS = None
        _CACHED_TOOL_MODELS = None
        _CACHED_UTILITY_MODELS = None
        _CACHED_IMAGE_MODELS = None

    return _get_cached_models()


# ==================== Public API ====================


def get_gen_models() -> list[ModelConfig]:
    """
    Get list of generation models.

    Returns:
        List of ModelConfig objects for generation models.
    """
    gen_models, _, _, _ = _get_cached_models()
    return list(gen_models.values())


def get_tool_models() -> list[ModelConfig]:
    """
    Get list of tool models.

    Returns:
        List of ModelConfig objects for tool-calling models.
    """
    _, tool_models, _, _ = _get_cached_models()
    return list(tool_models.values())


def get_utility_models() -> list[ModelConfig]:
    """
    Get list of utility models (lightweight, fast models).

    Returns:
        List of ModelConfig objects for utility models.
    """
    _, _, utility_models, _ = _get_cached_models()
    return list(utility_models.values())


def get_image_models() -> list[ModelConfig]:
    """
    Get list of image generation models.

    Returns:
        List of ModelConfig objects for image generation models.
    """
    _, _, _, image_models = _get_cached_models()
    return list(image_models.values())


def get_model_config(model_id: str) -> ModelConfig | None:
    """
    Get a specific model configuration by ID.

    Searches in all model categories (gen, tool, utility, image).

    Args:
        model_id: The unique identifier of the model.

    Returns:
        ModelConfig if found, None otherwise.
    """
    gen_models, tool_models, utility_models, image_models = _get_cached_models()

    # Search in all model categories
    for models in [gen_models, tool_models, utility_models, image_models]:
        if model_id in models:
            return models[model_id]

    return None


def get_model_full_config(model_id: str) -> dict[str, any]:
    """
    Get the full configuration for a model, suitable for API calls.

    Args:
        model_id: The unique identifier of the model.

    Returns:
        Dictionary containing:
            - api_key: str
            - base_url: str
            - model: str
            - temperature: float
            - max_tokens: int
            - supports_streaming: bool
            - supports_tools: bool
            - supports_json_mode: bool
            - supports_json_schema: bool

    Raises:
        ValueError: If model is not found.
    """
    model_config = get_model_config(model_id)

    if model_config is None:
        raise ValueError(f"Model not found: {model_id}")

    return {
        "api_key": model_config.api_key,
        "base_url": model_config.base_url,
        "model": model_config.model,
        "temperature": model_config.temperature,
        "max_tokens": model_config.max_tokens,
        "supports_streaming": model_config.supports_streaming,
        "supports_tools": model_config.supports_tools,
        "supports_json_mode": model_config.supports_json_mode,
        "supports_json_schema": model_config.supports_json_schema,
    }


def get_all_models() -> dict[str, list[ModelConfig]]:
    """
    Get all models organized by category.

    Returns:
        Dictionary with keys: 'gen', 'tool', 'utility', 'image'
    """
    gen_models, tool_models, utility_models, image_models = _get_cached_models()

    return {
        "gen": list(gen_models.values()),
        "tool": list(tool_models.values()),
        "utility": list(utility_models.values()),
        "image": list(image_models.values()),
    }
