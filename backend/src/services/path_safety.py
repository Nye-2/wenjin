"""Stable path-component normalization shared by workspace file services."""

from __future__ import annotations

import re

_INVALID_COMPONENT_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_path_component(value: str | None) -> str:
    """Return a safe, non-empty filesystem path component."""
    raw = str(value or "").strip()
    sanitized = _INVALID_COMPONENT_CHARS.sub("-", raw).strip(".-")
    return sanitized or "default"


__all__ = ["normalize_path_component"]
