"""Source import normalization helpers."""

from __future__ import annotations


def normalize_source_title(title: str) -> str:
    """Normalize title for source dedupe/search."""

    return " ".join(str(title or "").strip().lower().split())
