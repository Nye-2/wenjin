"""Execution-scoped token usage collection for workspace feature billing."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from src.services.thread_billing import (
    TokenUsage,
    combine_token_usage,
    extract_message_usage,
    normalize_token_usage,
)

_CURRENT_TOKEN_USAGES: ContextVar[list[TokenUsage] | None] = ContextVar(
    "current_token_usages",
    default=None,
)


def bind_token_usage_collector() -> Token[list[TokenUsage] | None]:
    """Start collecting token usage for the current async execution context."""
    return _CURRENT_TOKEN_USAGES.set([])


def reset_token_usage_collector(token: Token[list[TokenUsage] | None]) -> None:
    """Restore the previous token usage collection context."""
    _CURRENT_TOKEN_USAGES.reset(token)


def record_token_usage(value: Any) -> TokenUsage | None:
    """Record token usage from a provider response, usage dict, or TokenUsage."""
    if isinstance(value, TokenUsage):
        usage = value
    else:
        usage = extract_message_usage(value) or normalize_token_usage(value)
    if usage is None:
        return None

    usages = _CURRENT_TOKEN_USAGES.get()
    if usages is not None:
        usages.append(usage)
    return usage


def get_collected_token_usage() -> TokenUsage | None:
    """Return the combined token usage collected in this execution context."""
    usages = _CURRENT_TOKEN_USAGES.get()
    if not usages:
        return None
    return combine_token_usage(list(usages))
