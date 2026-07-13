"""LLM configuration loader for Wenjin.

This module parses model configurations from environment variables
(LLM_MODELS, LLM_IMAGE_MODELS) and provides access functions.

Configuration format (.env file):
    LLM_MODELS=[{"id":"gpt-5.6-sol","model":"gpt-5.6-sol","api_key":"sk-xxx","base_url":"https://api.example/v1","generation_api":"chat_completions"}]
    LLM_IMAGE_MODELS=[{"id":"image-model","model":"image-model","api_key":"sk-xxx","base_url":"https://images.example/v1"}]

Required fields: id, model, api_key, base_url
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from src.models.capability_profile import (
    CapabilityProfileAssessment,
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
    unverified_capability_assessment,
)
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    get_default_runtime_model_id,
    get_model_catalog_snapshot,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
    resolve_runtime_model_id,
)

logger = logging.getLogger(__name__)


class LLMSettings:
    """LLM global settings from environment."""

    TEMPERATURE: float = 0.7
    TIMEOUT: float = 120.0
    MAX_RETRIES: int = 3
    AGENT_TIMEOUT: float = 300.0
    TOOL_TIMEOUT: float = 60.0          # per-tool execution timeout in seconds
    TOOL_OUTPUT_MAX_CHARS: int = 10000   # truncate tool output above this

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
        if agent_timeout := os.environ.get("LLM_AGENT_TIMEOUT"):
            try:
                cls.AGENT_TIMEOUT = float(agent_timeout)
            except ValueError:
                pass
        if tool_timeout := os.environ.get("LLM_TOOL_TIMEOUT"):
            try:
                cls.TOOL_TIMEOUT = float(tool_timeout)
            except ValueError:
                pass
        if tool_max := os.environ.get("LLM_TOOL_OUTPUT_MAX_CHARS"):
            try:
                cls.TOOL_OUTPUT_MAX_CHARS = int(tool_max)
            except ValueError:
                pass


_env_loaded = False
_converted_model_cache_snapshot: object | None = None
_converted_model_cache: tuple[dict[str, "ModelConfig"], dict[str, "ModelConfig"]] | None = None
_invalid_explicit_default_model_id: str | None = None


def _maybe_load_env_file() -> None:
    """Load .env into process env for local/dev runtime consistency.

    We intentionally skip this in pytest to keep tests deterministic and
    independent from developer-specific local environment files.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    if "pytest" in sys.modules:
        return

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
        logger.debug("Loaded LLM env from %s", env_path)


class ModelConfig(BaseModel):
    """Model configuration with required and optional fields.

    Each model must have independent api_key and base_url.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

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
    timeout_seconds: float | None = None
    max_retries: int | None = None
    generation_api: GenerationAPI | None = Field(
        default=None,
        description="Verified language generation API; image models leave this unset",
    )
    capability_profile: ModelCapabilityProfile | None = None
    capability_probe: ModelCapabilityProbeEvidence | None = None
    default_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom HTTP headers for API requests (e.g. {'api-key': 'xxx'})",
    )
    pricing_policy_id: str | None = Field(default=None, description="Bound model_usage pricing policy id/key")

def _parse_model_from_json(data: dict[str, Any]) -> ModelConfig | None:
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
        catalog_only_fields = {
            "category",
            "enabled",
            "is_default",
            "pricing_policy_key",
            "provider",
            "provider_name",
            "trust_level",
        }
        payload = {
            key: value
            for key, value in data.items()
            if key not in catalog_only_fields
        }
        payload.setdefault("name", data.get("id", ""))
        return ModelConfig.model_validate(payload)
    except Exception as e:
        logger.warning("Failed to parse model config: %s. Skipping.", e)
        return None


def _load_models_from_env() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Load models from environment variables.

    Returns:
        Tuple of (llm_models, image_models)
    """
    llm_models: dict[str, ModelConfig] = {}
    image_models: dict[str, ModelConfig] = {}

    # Load LLM global settings
    _maybe_load_env_file()
    LLMSettings.load()

    # Parse LLM models from LLM_MODELS
    llm_models_json = os.environ.get("LLM_MODELS", "")
    if llm_models_json:
        try:
            models_data = json.loads(llm_models_json)
            for m in models_data:
                model_config = _parse_model_from_json(m)
                if model_config:
                    llm_models[model_config.id] = model_config
            logger.info("Loaded %d LLM models from LLM_MODELS", len(llm_models))
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM_MODELS JSON: %s", e)
    else:
        logger.debug("LLM_MODELS environment variable not set")

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

    return llm_models, image_models


def _get_cached_models() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Get cached model configurations from the runtime model catalog snapshot.

    Returns:
        Tuple of (llm_models, image_models)
    """
    global _converted_model_cache, _converted_model_cache_snapshot

    snapshot = get_model_catalog_snapshot()
    if (
        _converted_model_cache is not None
        and _converted_model_cache_snapshot is snapshot
    ):
        return _converted_model_cache

    llm_models = {
        model.id: _runtime_to_model_config(model)
        for model in snapshot.models(category="llm")
    }
    image_models = {
        model.id: _runtime_to_model_config(model)
        for model in snapshot.models(category="image")
    }
    _converted_model_cache_snapshot = snapshot
    _converted_model_cache = (llm_models, image_models)
    return _converted_model_cache


def reload_models() -> tuple[
    dict[str, ModelConfig],
    dict[str, ModelConfig],
]:
    """
    Reload model configurations from environment variables into the test snapshot.

    Production runtime should refresh `model_catalog_cache` from DataService. This
    helper remains for tests that explicitly install environment-shaped fixtures.

    Returns:
        Tuple of (llm_models, image_models)
    """
    global _converted_model_cache, _converted_model_cache_snapshot
    global _invalid_explicit_default_model_id

    _invalid_explicit_default_model_id = None
    llm_models, image_models = _load_models_from_env()
    explicit_default = os.environ.get("LLM_DEFAULT_MODEL", "").strip()
    if explicit_default and explicit_default not in llm_models and explicit_default not in image_models:
        _invalid_explicit_default_model_id = explicit_default
        _converted_model_cache_snapshot = None
        _converted_model_cache = None
        reset_model_catalog_cache()
        return {}, {}

    all_models: list[RuntimeModelConfig] = []
    default_id = explicit_default or (next(iter(llm_models.keys())) if llm_models else next(iter(image_models.keys()), ""))
    all_models.extend(
        _model_config_to_runtime(model, category="llm", is_default=model.id == default_id)
        for model in llm_models.values()
    )
    all_models.extend(
        _model_config_to_runtime(model, category="image", is_default=model.id == default_id)
        for model in image_models.values()
    )
    install_model_catalog_snapshot(all_models)
    _converted_model_cache_snapshot = None
    _converted_model_cache = None

    return _get_cached_models()


# ==================== Public API ====================


def get_llm_models() -> list[ModelConfig]:
    """
    Get list of LLM models (text generation / chat / tool-calling).

    Returns:
        List of ModelConfig objects for LLM models.
    """
    llm_models, _ = _get_cached_models()
    return list(llm_models.values())


def get_image_models() -> list[ModelConfig]:
    """
    Get list of image generation models.

    Returns:
        List of ModelConfig objects for image generation models.
    """
    _, image_models = _get_cached_models()
    return list(image_models.values())


def get_model_config(model_id: str) -> ModelConfig | None:
    """
    Get a specific model configuration by ID.

    Searches in all model categories (llm, image).

    Args:
        model_id: The unique identifier of the model.

    Returns:
        ModelConfig if found, None otherwise.
    """
    llm_models, image_models = _get_cached_models()

    if model_id in llm_models:
        return llm_models[model_id]
    if model_id in image_models:
        return image_models[model_id]

    return None


def get_model_full_config(model_id: str) -> dict[str, Any]:
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
            - generation_api: str | None
            - capability_profile: object
            - capability_probe: object

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
        "timeout_seconds": model_config.timeout_seconds,
        "max_retries": model_config.max_retries,
        "generation_api": model_config.generation_api,
        "capability_profile": model_config.capability_profile,
        "capability_probe": model_config.capability_probe,
        "default_headers": dict(model_config.default_headers or {}),
    }


def get_all_models() -> dict[str, list[ModelConfig]]:
    """
    Get all models organized by category.

    Returns:
        Dictionary with keys: 'llm', 'image'
    """
    llm_models, image_models = _get_cached_models()

    return {"llm": list(llm_models.values()), "image": list(image_models.values())}


def get_default_model_id() -> str:
    """Resolve the default chat model id from environment-backed model config.

    Priority:
    1. ``LLM_DEFAULT_MODEL`` when it points to a configured model id
    2. First LLM model
    3. First image model

    Returns:
        Model id string.

    Raises:
        ValueError: If no models are configured.
    """
    if _invalid_explicit_default_model_id:
        raise ValueError(
            f"LLM_DEFAULT_MODEL is not configured: {_invalid_explicit_default_model_id}"
        )

    try:
        return get_default_runtime_model_id()
    except ValueError as exc:
        raise ValueError("No models configured in model catalog cache") from exc


def resolve_model_id(model_id: str | None) -> str:
    """Normalize requested model id without silently rerouting unknown ids."""
    return resolve_runtime_model_id(model_id)


def _runtime_to_model_config(model: RuntimeModelConfig) -> ModelConfig:
    return ModelConfig(
        id=model.id,
        model=model.model,
        api_key=model.api_key,
        base_url=model.base_url,
        name=model.name,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        timeout_seconds=model.timeout_seconds,
        max_retries=model.max_retries,
        generation_api=model.generation_api,
        capability_profile=model.capability_profile,
        capability_probe=model.capability_probe,
        default_headers=model.default_headers,
        pricing_policy_id=model.pricing_policy_id,
    )


def _model_config_to_runtime(model: ModelConfig, *, category: str, is_default: bool) -> RuntimeModelConfig:
    assessment = _model_config_assessment(model)
    return RuntimeModelConfig(
        id=model.id,
        name=model.name or model.id,
        category=category,
        provider="Custom",
        model=model.model,
        api_key=model.api_key,
        base_url=model.base_url,
        generation_api=model.generation_api,
        max_tokens=model.max_tokens,
        temperature=model.temperature,
        timeout_seconds=model.timeout_seconds,
        max_retries=model.max_retries,
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
        default_headers=dict(model.default_headers or {}),
        pricing_policy_id=model.pricing_policy_id,
        is_default=is_default,
        config_version=1,
    )


def _model_config_assessment(model: ModelConfig) -> CapabilityProfileAssessment:
    if model.capability_profile is not None and model.capability_probe is not None:
        return CapabilityProfileAssessment(
            profile=model.capability_profile,
            evidence=model.capability_probe,
        )
    if model.capability_profile is not None or model.capability_probe is not None:
        raise ValueError("capability_profile and capability_probe must be configured together")
    return unverified_capability_assessment(
        model_id=model.id,
        model_name=model.model,
        base_url=model.base_url,
        generation_api=model.generation_api,
    )
