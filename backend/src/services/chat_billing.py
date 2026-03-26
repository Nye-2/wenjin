"""Helpers for extracting chat token usage and exposing billing-friendly summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TokenUsage:
    """Normalized token accounting for one chat turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return a JSON-serializable representation."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


def _coerce_int(value: Any) -> int:
    """Coerce token counters into non-negative ints."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def normalize_token_usage(raw: Any) -> TokenUsage | None:
    """Normalize provider-specific token payloads into a common structure."""
    if not isinstance(raw, dict):
        return None

    input_tokens = _coerce_int(
        raw.get("input_tokens", raw.get("prompt_tokens", raw.get("input", 0)))
    )
    output_tokens = _coerce_int(
        raw.get(
            "output_tokens",
            raw.get("completion_tokens", raw.get("output", 0)),
        )
    )
    total_tokens = _coerce_int(raw.get("total_tokens", raw.get("total", 0)))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _usage_from_response_metadata(raw: Any) -> TokenUsage | None:
    """Extract usage from provider response metadata shapes."""
    if not isinstance(raw, dict):
        return None
    for candidate in (
        raw.get("token_usage"),
        raw.get("usage"),
        raw.get("usage_metadata"),
        raw,
    ):
        usage = normalize_token_usage(candidate)
        if usage is not None:
            return usage
    return None


def extract_message_usage(message: Any) -> TokenUsage | None:
    """Extract usage from an AI message or response object."""
    usage = normalize_token_usage(getattr(message, "usage_metadata", None))
    if usage is not None:
        return usage

    usage = _usage_from_response_metadata(getattr(message, "response_metadata", None))
    if usage is not None:
        return usage

    if isinstance(message, dict):
        for key in ("usage_metadata", "response_metadata", "token_usage", "usage"):
            usage = _usage_from_response_metadata(message.get(key))
            if usage is not None:
                return usage
    return None


def combine_token_usage(usages: list[TokenUsage]) -> TokenUsage | None:
    """Combine multiple message-level usages into one turn-level summary."""
    if not usages:
        return None

    return TokenUsage(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
    )


def extract_usage_from_agent_result(result: dict[str, Any]) -> TokenUsage | None:
    """Aggregate token usage across all model messages in an agent result."""
    if not isinstance(result, dict):
        return None

    usages: list[TokenUsage] = []
    for message in result.get("messages") or []:
        usage = extract_message_usage(message)
        if usage is not None:
            usages.append(usage)

    combined = combine_token_usage(usages)
    if combined is not None:
        return combined

    for key in ("usage_metadata", "response_metadata", "token_usage", "usage"):
        usage = _usage_from_response_metadata(result.get(key))
        if usage is not None:
            return usage
    return None


def usage_to_metadata(
    usage: TokenUsage,
    *,
    model_name: str | None = None,
    source: str = "chat",
) -> dict[str, Any]:
    """Build persisted chat metadata for a measured turn."""
    payload: dict[str, Any] = usage.as_dict()
    payload["source"] = source
    if model_name:
        payload["model_name"] = model_name
    return payload
