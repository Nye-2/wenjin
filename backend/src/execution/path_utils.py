"""Path normalization helpers for execution sandboxes."""

from __future__ import annotations

import re

_INVALID_COMPONENT_CHARS = re.compile(r"[^a-zA-Z0-9_.-]+")


def normalize_thread_id(thread_id: str | None) -> str:
    """Normalize thread id into a safe path component."""
    raw = str(thread_id or "").strip()
    sanitized = _INVALID_COMPONENT_CHARS.sub("-", raw).strip(".-")
    return sanitized or "default"

