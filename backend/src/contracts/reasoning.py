"""Canonical reasoning-effort contract shared by model and Mission runtimes."""

from __future__ import annotations

from enum import StrEnum


class ReasoningEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


DEFAULT_REASONING_EFFORT = ReasoningEffort.XHIGH


def normalize_reasoning_effort(
    value: str | ReasoningEffort | None,
    *,
    default: ReasoningEffort | None = None,
) -> ReasoningEffort | None:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    try:
        return ReasoningEffort(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ReasoningEffort)
        raise ValueError(
            f"Unsupported reasoning_effort: {value}. Expected one of: {allowed}"
        ) from exc


__all__ = [
    "DEFAULT_REASONING_EFFORT",
    "ReasoningEffort",
    "normalize_reasoning_effort",
]
