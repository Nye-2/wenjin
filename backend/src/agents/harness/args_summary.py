"""Bounded tool argument summaries for harness records."""

from __future__ import annotations

import hashlib
import json
from typing import Any

TEXT_PAYLOAD_ARG_KEYS = frozenset({"content", "markdown", "script", "text"})
STRUCTURED_PAYLOAD_ARG_KEYS = frozenset({"dependency_hints", "edits"})


def summarize_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Return debug-safe tool args for records and events."""

    summary: dict[str, Any] = {}
    for key, value in args.items():
        if key in TEXT_PAYLOAD_ARG_KEYS and isinstance(value, str):
            summary[key] = _text_payload_digest(value)
        elif key in STRUCTURED_PAYLOAD_ARG_KEYS:
            summary[key] = _structured_payload_digest(value)
        elif isinstance(value, str) and len(value) > 500:
            summary[key] = f"{value[:500]}... ({len(value)} chars)"
        else:
            summary[key] = value
    return summary


def _text_payload_digest(value: str) -> dict[str, Any]:
    return {
        "redacted": True,
        "chars": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


def _structured_payload_digest(value: Any) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    payload = {
        "redacted": True,
        "kind": type(value).__name__,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    if isinstance(value, (list, tuple, set, frozenset)):
        payload["items"] = len(value)
    return payload
