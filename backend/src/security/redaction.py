"""Utilities for removing secrets from user-facing payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED_SECRET = "[redacted]"

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(authorization|api[-_\s]?key|access[-_\s]?key|secret|token|password|credential)",
    re.IGNORECASE,
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"\b(?:Bearer|Token|Basic)\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[-_\s]?key|token|authorization|credential|password|secret)\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk|tp|ak|rk|pk)-[A-Za-z0-9._=-]{8,}\b", re.IGNORECASE),
)


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key usually contains secret material."""

    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def redact_secret_text(value: Any) -> str:
    """Redact recognizable secret values inside free-form text."""

    text = "" if value is None else str(value)
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub(REDACTED_SECRET, text)
    return text


def redact_sensitive_headers(headers: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a copy of headers with secret-bearing entries redacted."""

    if not headers:
        return {}
    safe: dict[str, Any] = {}
    for key, value in headers.items():
        key_text = str(key)
        if is_sensitive_key(key_text):
            safe[key_text] = REDACTED_SECRET
            continue
        safe[key_text] = _redact_header_value(value)
    return safe


def _redact_header_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, list | tuple):
        return [redact_secret_text(item) for item in value]
    return redact_secret_text(value)
