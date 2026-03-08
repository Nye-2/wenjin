"""LLM configuration loader for AcademiaGPT v2.

This module parses model configurations from environment variables
(LLM_GEN_MODELS, LLM_TOOL_MODELS) and provides access functions.

Configuration format (.env file):
    LLM_GEN_MODELS=[{"id":"deepseek-v3","model":"deepseek/deepseek-v3","api_key":"sk-xxx","base_url":"https://api.deepseek.com"}]
    LLM_TOOL_MODELS=[{"id":"kimi-k2.5","model":"openai/moonshotai/kimi-k2.5","api_key":"sk-xxx","base_url":"https://api.moonshot.cn/v1"}]

Required fields: id, model, api_key, base_url
"""

import json
import logging
import os
import threading
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
    temperature: float = Field(default=0.7, description="Default temperature")
    max_tokens: int = Field(default=32768, description="Maximum output tokens")
    supports_streaming: bool = Field(default=True, description="Supports streaming output")
    supports_tools: bool = Field(default=False, description="Supports tool/function calling")
    supports_json_mode: bool = Field(default=True, description="Supports JSON response format")
    supports_json_schema: bool = Field(default=False, description="Supports JSON schema response format")


def _parse_model_from_json(data: dict) -> Optional[ModelConfig]:
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
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 32768),
            supports_streaming=data.get("supports_streaming", True),
            supports_tools=data.get("supports_tools", False),
            supports_json_mode=data.get("supports_json_mode", True),
            supports_json_schema=data.get("supports_json_schema", False),
        )
    except Exception as e:
        logger.warning("Failed to parse model config: %s. Skipping.", e)
        return None


def _load_models_from_env() -> tuple[Dict[str, ModelConfig], Dict[str, ModelConfig]]:
    """
    Load models from environment variables.

    Returns:
        Tuple of (gen_models dict, tool_models dict)
    """
    gen_models: Dict[str, ModelConfig] = {}
    tool_models: Dict[str, ModelConfig] = {}

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

    return gen_models, tool_models


# Global cache with thread-safe access
_CACHED_GEN_MODELS: Optional[Dict[str, ModelConfig]] = None
_CACHED_TOOL_MODELS: Optional[Dict[str, ModelConfig]] = None
_cache_lock = threading.Lock()


def _get_cached_models() -> tuple[Dict[str, ModelConfig], Dict[str, ModelConfig]]:
    """
    Get cached model configurations (lazy loading, thread-safe).

    Returns:
        Tuple of (gen_models dict, tool_models dict)
    """
    global _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS

    if _CACHED_GEN_MODELS is None:
        with _cache_lock:
            # Double-check after acquiring lock
            if _CACHED_GEN_MODELS is None:
                _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS = _load_models_from_env()

    return _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS


def reload_models() -> tuple[Dict[str, ModelConfig], Dict[str, ModelConfig]]:
    """
    Reload model configurations from environment variables.

    This clears the cache and reloads models, useful for hot-reloading
    configuration changes without restarting the application.

    Returns:
        Tuple of (gen_models dict, tool_models dict)
    """
    global _CACHED_GEN_MODELS, _CACHED_TOOL_MODELS

    with _cache_lock:
        _CACHED_GEN_MODELS = None
        _CACHED_TOOL_MODELS = None

    return _get_cached_models()


# ==================== Public API ====================


def get_gen_models() -> List[ModelConfig]:
    """
    Get list of generation models.

    Returns:
        List of ModelConfig objects for generation models.
    """
    gen_models, _ = _get_cached_models()
    return list(gen_models.values())


def get_tool_models() -> List[ModelConfig]:
    """
    Get list of tool models.

    Returns:
        List of ModelConfig objects for tool-calling models.
    """
    _, tool_models = _get_cached_models()
    return list(tool_models.values())


def get_model_config(model_id: str) -> Optional[ModelConfig]:
    """
    Get a specific model configuration by ID.

    Searches in both generation and tool models.

    Args:
        model_id: The unique identifier of the model.

    Returns:
        ModelConfig if found, None otherwise.
    """
    gen_models, tool_models = _get_cached_models()

    # Search in gen models first, then tool models
    if model_id in gen_models:
        return gen_models[model_id]
    if model_id in tool_models:
        return tool_models[model_id]

    return None


def get_model_full_config(model_id: str) -> Dict[str, any]:
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
