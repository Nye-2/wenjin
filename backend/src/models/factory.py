"""Create chat models from probe-backed Model Catalog entries."""

import logging
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from src.config.llm_config import LLMSettings, get_model_full_config, resolve_model_id
from src.contracts.reasoning import (
    DEFAULT_REASONING_EFFORT,
    ReasoningEffort,
    normalize_reasoning_effort,
)
from src.models.capability_profile import (
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
    assess_profile_freshness,
)

logger = logging.getLogger(__name__)

def create_chat_model(
    model_id: str,
    temperature: float | None = None,
    reasoning_effort: str | ReasoningEffort | None = None,
    request_timeout: float | None = None,
    max_retries: int | None = None,
    max_output_tokens: int | None = None,
) -> BaseChatModel:
    """Create a chat model instance based on dynamic configuration.

    This function uses get_model_full_config() from llm_config to get
    the model configuration, then creates the appropriate LLM instance.

    Args:
        model_id: The unique identifier of the model (as defined in env config)
        temperature: Optional temperature override. If not provided, uses
                     the temperature from the model config.
        reasoning_effort: Optional verified reasoning effort.
        request_timeout: Optional per-request timeout override in seconds.
        max_retries: Optional retry override for this model instance.
        max_output_tokens: Optional call-level output budget, bounded by the
            model catalog limit.

    Returns:
        Configured Chat Completions model instance.

    Raises:
        ValueError: If the model is not found in the configuration

    Example:
        >>> model = create_chat_model("gpt-5.6-sol", reasoning_effort="xhigh")
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
    catalog_max_tokens = int(config.get("max_tokens", 4096))
    max_tokens = _max_output_tokens_value(
        max_output_tokens,
        catalog_max_tokens=catalog_max_tokens,
    )

    # Use provided temperature or fall back to config default
    actual_temperature = temperature if temperature is not None else config_temperature
    actual_timeout = _request_timeout_value(
        request_timeout
        if request_timeout is not None
        else config.get("timeout_seconds")
    )
    actual_max_retries = _max_retries_value(
        max_retries
        if max_retries is not None
        else config.get("max_retries")
    )

    generation_api = config.get("generation_api")
    if generation_api is not GenerationAPI.CHAT_COMPLETIONS:
        raise ValueError(
            f"Model '{resolved_model_id}' is not verified for Chat Completions"
        )
    profile = config.get("capability_profile")
    evidence = config.get("capability_probe")
    if not isinstance(profile, ModelCapabilityProfile) or not isinstance(
        evidence, ModelCapabilityProbeEvidence
    ):
        raise ValueError(
            f"Model '{resolved_model_id}' has no typed capability assessment"
        )
    freshness = assess_profile_freshness(
        profile,
        evidence,
        model_id=resolved_model_id,
        model_name=model_string,
        base_url=base_url,
        generation_api=generation_api,
    )
    if not freshness.current or not profile.protocol_conformance:
        reasons = ", ".join(freshness.reasons) or "protocol_not_conformant"
        raise ValueError(
            f"Model '{resolved_model_id}' capability assessment is unavailable: {reasons}"
        )
    if not profile.response_storage_disabled:
        raise ValueError(
            f"Model '{resolved_model_id}' has not verified store=false handling"
        )

    resolved_reasoning_effort = normalize_reasoning_effort(reasoning_effort)
    if profile.accepts_reasoning_effort(DEFAULT_REASONING_EFFORT) and resolved_reasoning_effort is None:
        resolved_reasoning_effort = DEFAULT_REASONING_EFFORT
    if resolved_reasoning_effort is not None and not profile.accepts_reasoning_effort(
        resolved_reasoning_effort
    ):
        raise ValueError(
            f"Model '{resolved_model_id}' has no current probe for reasoning effort "
            f"'{resolved_reasoning_effort}'"
        )

    return _create_chat_completions_model(
        model_string=model_string,
        api_key=api_key,
        base_url=base_url,
        temperature=actual_temperature,
        max_tokens=max_tokens,
        reasoning_effort=(
            resolved_reasoning_effort.value
            if resolved_reasoning_effort is not None
            else None
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


def _max_output_tokens_value(
    value: int | None,
    *,
    catalog_max_tokens: int,
) -> int:
    if value is None:
        return catalog_max_tokens
    try:
        requested = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_output_tokens must be a positive integer") from exc
    if requested < 1:
        raise ValueError("max_output_tokens must be a positive integer")
    return min(requested, catalog_max_tokens)


class ReasoningChatOpenAI(ChatOpenAI):
    """Preserve the release endpoint's streamed ``reasoning_content`` field."""

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


def _create_chat_completions_model(
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
    """Create the sole verified Chat Completions runtime adapter.

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
        "Creating Chat Completions model: %s (base_url: %s)",
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
        "http_client": httpx.Client(
            timeout=_request_timeout_value(request_timeout),
            trust_env=False,
        ),
        "http_async_client": httpx.AsyncClient(
            timeout=_request_timeout_value(request_timeout),
            trust_env=False,
        ),
    }
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if default_headers:
        kwargs["default_headers"] = default_headers
    return ReasoningChatOpenAI(**kwargs)
