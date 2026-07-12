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


def redact_tool_value(value: Any, *, max_text_chars: int = 2000) -> Any:
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
                )
        return redacted
    if isinstance(value, list | tuple):
        return [redact_tool_value(item, max_text_chars=max_text_chars) for item in value[:100]]
    if isinstance(value, str):
        return redact_secret_text(value)[:max_text_chars]
    return value


__all__ = ["redact_tool_value"]
