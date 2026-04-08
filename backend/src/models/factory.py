"""Model factory for creating LLM instances.

This module provides a factory function to create LLM instances
based on dynamic configuration loaded from environment variables.

The factory uses the llm_config module to get model configurations,
supporting:
- OpenAI-compatible APIs (DeepSeek, GLM, Qwen, etc.) via ChatOpenAI
- Anthropic/Claude models via ChatAnthropic with extended thinking support
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config.llm_config import LLMSettings, get_model_full_config, resolve_model_id

logger = logging.getLogger(__name__)

# Default thinking budget for Claude models with extended thinking
DEFAULT_THINKING_BUDGET = 10000
DEFAULT_ANTHROPIC_BETAS = ["interleaved-thinking-2025-05-14"]


def _is_anthropic_provider(base_url: str, model: str) -> bool:
    """Determine if the model is an Anthropic model.

    Args:
        base_url: The base URL of the API
        model: The model string

    Returns:
        True if this is an Anthropic model, False otherwise
    """
    # Check by base_url first (most reliable)
    if "anthropic" in base_url.lower():
        return True

    # Check by model string prefix
    model_lower = model.lower()
    if model_lower.startswith("claude") or "anthropic" in model_lower:
        return True

    return False


def _is_minimax_provider(base_url: str, model: str) -> bool:
    """Determine if the model uses MiniMax's OpenAI-compatible endpoint."""
    base_url_lower = (base_url or "").lower()
    model_lower = (model or "").lower()
    return "minimaxi" in base_url_lower or model_lower.startswith("minimax-")


def _supports_reasoning_effort(config: dict[str, Any]) -> bool:
    """Infer whether the model accepts reasoning_effort."""
    if bool(config.get("supports_reasoning_effort", False)):
        return True

    model_string = str(config.get("model", "") or "").lower()
    return "gpt-5" in model_string or "doubao" in model_string


def create_chat_model(
    model_id: str,
    temperature: float | None = None,
    thinking_enabled: bool = False,
    reasoning_effort: str | None = None,
) -> BaseChatModel:
    """Create a chat model instance based on dynamic configuration.

    This function uses get_model_full_config() from llm_config to get
    the model configuration, then creates the appropriate LLM instance.

    Args:
        model_id: The unique identifier of the model (as defined in env config)
        temperature: Optional temperature override. If not provided, uses
                     the temperature from the model config.
        thinking_enabled: Whether to enable extended thinking for Claude models.
                         When enabled, adds thinking and betas parameters.
        reasoning_effort: Optional reasoning effort for GPT-5/Doubao-style models.

    Returns:
        Configured chat model instance (ChatOpenAI or ChatAnthropic)

    Raises:
        ValueError: If the model is not found in the configuration

    Example:
        >>> model = create_chat_model("deepseek-v3", temperature=0.7)
        >>> model = create_chat_model("claude-sonnet-4", thinking_enabled=True)
    """
    # Resolve the configured/default alias and get full model configuration
    resolved_model_id = resolve_model_id(model_id)

    # Get the full configuration for this model
    try:
        config = get_model_full_config(resolved_model_id)
    except ValueError as e:
        logger.error("Model not found after resolution: %s", resolved_model_id)
        raise ValueError(f"Model not found: {resolved_model_id}") from e

    # Extract configuration values
    model_string = config["model"]
    api_key = config["api_key"]
    base_url = config["base_url"]
    config_temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens", 4096)

    # Use provided temperature or fall back to config default
    actual_temperature = temperature if temperature is not None else config_temperature

    # Determine if this is an Anthropic model
    is_anthropic = _is_anthropic_provider(base_url, model_string)
    supports_reasoning_effort = _supports_reasoning_effort(config)
    resolved_reasoning_effort = (
        reasoning_effort.strip()
        if isinstance(reasoning_effort, str) and reasoning_effort.strip()
        else None
    )
    if supports_reasoning_effort and resolved_reasoning_effort is None:
        resolved_reasoning_effort = "minimal"

    if is_anthropic:
        return _create_anthropic_model(
            model_string=model_string,
            api_key=api_key,
            base_url=base_url,
            temperature=actual_temperature,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )
    else:
        return _create_openai_compatible_model(
            model_string=model_string,
            api_key=api_key,
            base_url=base_url,
            temperature=actual_temperature,
            max_tokens=max_tokens,
            reasoning_effort=(
                resolved_reasoning_effort if supports_reasoning_effort else None
            ),
        )


def _create_openai_compatible_model(
    model_string: str,
    api_key: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None = None,
) -> ChatOpenAI:
    """Create an OpenAI-compatible model instance.

    Used for DeepSeek, GLM, Qwen, and other OpenAI-compatible APIs.

    Args:
        model_string: The model identifier string
        api_key: API key for authentication
        base_url: Base URL for the API
        temperature: Sampling temperature
        max_tokens: Maximum output tokens

    Returns:
        Configured ChatOpenAI instance
    """
    logger.debug(
        "Creating OpenAI-compatible model: %s (base_url: %s)",
        model_string,
        base_url,
    )

    kwargs: dict[str, Any] = {
        "model": model_string,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": LLMSettings.TIMEOUT,
        "max_retries": LLMSettings.MAX_RETRIES,
    }
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if _is_minimax_provider(base_url, model_string):
        kwargs["extra_body"] = {"reasoning_split": True}

    return ChatOpenAI(
        **kwargs,
    )


def _create_anthropic_model(
    model_string: str,
    api_key: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    thinking_enabled: bool,
) -> BaseChatModel:
    """Create an Anthropic/Claude model instance.

    Supports extended thinking mode for Claude models.

    Args:
        model_string: The model identifier string
        api_key: API key for authentication
        base_url: Base URL for the API
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        thinking_enabled: Whether to enable extended thinking

    Returns:
        Configured ChatAnthropic instance
    """
    from langchain_anthropic import ChatAnthropic

    logger.debug(
        "Creating Anthropic model: %s (thinking_enabled: %s)",
        model_string,
        thinking_enabled,
    )

    kwargs: dict[str, Any] = {
        "model": model_string,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "default_request_timeout": LLMSettings.TIMEOUT,
        "max_retries": LLMSettings.MAX_RETRIES,
    }

    # LangChain Anthropic expects extended thinking under the `thinking` field.
    if thinking_enabled:
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": DEFAULT_THINKING_BUDGET,
        }
        kwargs["betas"] = DEFAULT_ANTHROPIC_BETAS
        logger.debug(
            "Extended thinking enabled with budget=%d",
            DEFAULT_THINKING_BUDGET,
        )

    return ChatAnthropic(**kwargs)
