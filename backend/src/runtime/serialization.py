"""Canonical serialization for runtime streaming and state payloads."""

from __future__ import annotations

import json
from typing import Any


def serialize_lc_object(obj: Any) -> Any:
    """Recursively serialize objects into JSON-safe values."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(key): serialize_lc_object(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_lc_object(item) for item in obj]

    if hasattr(obj, "model_dump"):
        try:
            return serialize_lc_object(obj.model_dump())
        except Exception:
            pass

    if hasattr(obj, "dict"):
        try:
            return serialize_lc_object(obj.dict())
        except Exception:
            pass

    try:
        return str(obj)
    except Exception:
        return repr(obj)


def serialize_public_values(values: dict[str, Any]) -> dict[str, Any]:
    """Serialize public values while stripping internal runtime keys."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        if str(key).startswith("__"):
            continue
        result[str(key)] = serialize_lc_object(value)
    return result


def serialize_messages_tuple(obj: Any) -> Any:
    """Serialize messages-mode tuple ``(chunk, metadata)``."""
    if isinstance(obj, tuple) and len(obj) == 2:
        chunk, metadata = obj
        safe_metadata = metadata if isinstance(metadata, dict) else {}
        return [serialize_lc_object(chunk), serialize_lc_object(safe_metadata)]
    return serialize_lc_object(obj)


def serialize(obj: Any, *, mode: str = "") -> Any:
    """Serialize with mode-specific behavior."""
    if mode == "messages":
        return serialize_messages_tuple(obj)
    if mode == "values":
        if isinstance(obj, dict):
            return serialize_public_values(obj)
    return serialize_lc_object(obj)


def dumps_json(obj: Any, *, mode: str = "", ensure_ascii: bool = True) -> str:
    """Serialize to a stable JSON string."""
    return json.dumps(
        serialize(obj, mode=mode),
        ensure_ascii=ensure_ascii,
        default=str,
    )


def encode_sse_data(
    payload: Any,
    *,
    mode: str = "",
    ensure_ascii: bool = True,
) -> str:
    """Encode one SSE data frame."""
    return f"data: {dumps_json(payload, mode=mode, ensure_ascii=ensure_ascii)}\n\n"
