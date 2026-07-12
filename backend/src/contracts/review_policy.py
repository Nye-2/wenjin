"""Workspace-level defaults for Mission review policy."""

from __future__ import annotations

from typing import Literal, cast, get_args

ReviewMode = Literal["review_all", "balanced_default", "auto_draft"]
DEFAULT_REVIEW_MODE: ReviewMode = "balanced_default"
VALID_REVIEW_MODES = frozenset(get_args(ReviewMode))


def normalize_review_mode(value: object | None) -> ReviewMode:
    raw = DEFAULT_REVIEW_MODE if value is None else str(value).strip()
    if raw not in VALID_REVIEW_MODES:
        raise ValueError(
            f"Invalid review_mode: {value}. Must be one of: {sorted(VALID_REVIEW_MODES)}"
        )
    return cast(ReviewMode, raw)


__all__ = ["DEFAULT_REVIEW_MODE", "ReviewMode", "normalize_review_mode"]
