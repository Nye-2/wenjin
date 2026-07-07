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
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
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


def _supports_reasoning_effort(config: dict[str, Any]) -> bool:
    """Return whether the configured model accepts reasoning_effort."""

    return bool(config.get("supports_reasoning_effort", False))


def create_chat_model(
    model_id: str,
    temperature: float | None = None,
    thinking_enabled: bool = False,
    reasoning_effort: str | None = None,
    request_timeout: float | None = None,
    max_retries: int | None = None,
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
        request_timeout: Optional per-request timeout override in seconds.
        max_retries: Optional retry override for this model instance.

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
    actual_timeout = _request_timeout_value(request_timeout)
    actual_max_retries = _max_retries_value(max_retries)

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
            request_timeout=actual_timeout,
            max_retries=actual_max_retries,
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
            default_headers=config.get("default_headers"),
            request_timeout=actual_timeout,
            max_retries=actual_max_retries,
        )


def _request_timeout_value(value: float | None) -> float:
    try:
        timeout = float(value) if value is not None else float(LLMSettings.TIMEOUT)
    except (TypeError, ValueError):
        timeout = float(LLMSettings.TIMEOUT)
    return max(1.0, timeout)


def _max_retries_value(value: int | None) -> int:
    try:
        retries = int(value) if value is not None else int(LLMSettings.MAX_RETRIES)
    except (TypeError, ValueError):
        retries = int(LLMSettings.MAX_RETRIES)
    return max(0, retries)


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI that extracts reasoning_content from API responses.

    Some OpenAI-compatible APIs (e.g. DeepSeek V4 Pro via qnaigc.com)
    return reasoning content in a separate ``reasoning_content`` field
    on the message / delta.  LangChain's built-in ChatOpenAI silently
    drops that field.  This subclass forwards it into
    ``additional_kwargs["reasoning"]`` so that downstream extractors
    (e.g. ``_extract_reasoning_text`` in the thread handler) can find it.
    """

    def _create_chat_result(
        self,
        response: Any,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        # Pull reasoning_content from the raw response and attach it to
        # each generation's message.additional_kwargs.
        response_dict = (
            response if isinstance(response, dict) else response.model_dump()
        )
        for idx, choice in enumerate(response_dict.get("choices", [])):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning and idx < len(result.generations):
                msg = result.generations[idx].message
                if isinstance(msg, AIMessage):
                    msg.additional_kwargs["reasoning"] = reasoning
        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None = None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None:
            return None

        # Streamed reasoning_content appears in delta.reasoning_content.
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if choices:
            delta = choices[0].get("delta", {}) or {}
            reasoning = delta.get("reasoning_content")
            if reasoning:
                msg = generation_chunk.message
                if isinstance(msg, AIMessageChunk):
                    msg.additional_kwargs.setdefault("reasoning", "")
                    msg.additional_kwargs["reasoning"] += reasoning
        return generation_chunk

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = self._convert_input(input_).to_messages()
        for original_message, payload_message in zip(messages, payload.get("messages", []), strict=False):
            if not isinstance(original_message, AIMessage):
                continue
            reasoning_content = original_message.additional_kwargs.get("reasoning_content")
            if not isinstance(reasoning_content, str) or not reasoning_content.strip():
                reasoning = original_message.additional_kwargs.get("reasoning")
                if isinstance(reasoning, str) and reasoning.strip():
                    reasoning_content = reasoning
                else:
                    reasoning_content = None
            if reasoning_content:
                payload_message["reasoning_content"] = reasoning_content
        return payload


def _create_openai_compatible_model(
    model_string: str,
    api_key: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None = None,
    default_headers: dict[str, str] | None = None,
    request_timeout: float | None = None,
    max_retries: int | None = None,
) -> ChatOpenAI:
    """Create an OpenAI-compatible model instance.

    Used for DeepSeek, GLM, Qwen, and other OpenAI-compatible APIs.

    Args:
        model_string: The model identifier string
        api_key: API key for authentication
        base_url: Base URL for the API
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        default_headers: Custom HTTP headers for API requests

    Returns:
        Configured ReasoningChatOpenAI instance
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
        "timeout": _request_timeout_value(request_timeout),
        "max_retries": _max_retries_value(max_retries),
        "store": False,
    }
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    # Pass through custom headers (e.g. api-key for non-standard endpoints)
    if default_headers:
        kwargs["default_headers"] = default_headers
    return ReasoningChatOpenAI(
        **kwargs,
    )


def _create_anthropic_model(
    model_string: str,
    api_key: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    thinking_enabled: bool,
    request_timeout: float | None = None,
    max_retries: int | None = None,
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
        "default_request_timeout": _request_timeout_value(request_timeout),
        "max_retries": _max_retries_value(max_retries),
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
