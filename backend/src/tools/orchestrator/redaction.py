"""Bounded recursive redaction for tool outcomes and diagnostics."""

from __future__ import annotations

from typing import Any

from src.security.redaction import redact_secret_text

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


def redact_tool_value(
    value: Any,
    *,
    max_text_chars: int | None = None,
    max_items: int | None = None,
) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEYS):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_tool_value(
                    item,
                    max_text_chars=max_text_chars,
                    max_items=max_items,
                )
        return redacted
    if isinstance(value, list | tuple):
        items = value if max_items is None else value[:max_items]
        return [
            redact_tool_value(
                item,
                max_text_chars=max_text_chars,
                max_items=max_items,
            )
            for item in items
        ]
    if isinstance(value, str):
        redacted = redact_secret_text(value)
        return redacted if max_text_chars is None else redacted[:max_text_chars]
    return value


__all__ = ["redact_tool_value"]
