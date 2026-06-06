"""Output bounding helpers for harness tools."""

from __future__ import annotations


def cap_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Return a bounded text preview and whether it was truncated."""

    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def select_lines(
    content: str,
    *,
    start_line: int | None,
    end_line: int | None,
) -> str:
    """Return a 1-based inclusive line window from content."""

    if start_line is None and end_line is None:
        return content
    lines = content.splitlines(keepends=True)
    start = max((start_line or 1) - 1, 0)
    end = min(end_line or len(lines), len(lines))
    return "".join(lines[start:end])
