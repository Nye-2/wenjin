"""File-change attribution helpers for harness write tools."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from typing import Any


def build_file_change(
    *,
    path: str,
    before: str | None,
    after: str,
    operation: str,
) -> dict[str, Any]:
    """Build the compact file-change record stored with harness tool calls."""

    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff = "".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path.removeprefix('/')}",
            tofile=f"b/{path.removeprefix('/')}",
        )
    )
    return {
        "path": path,
        "operation": operation,
        "before_hash": _sha256(before),
        "after_hash": _sha256(after),
        "unified_diff": diff,
    }


def _sha256(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
