"""Shared invariants for inserting committed academic visuals into Prism."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import quote

from src.contracts.prism_context import prism_selection_hash, split_utf8_selection

_VISUAL_SUFFIX_BY_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


def canonical_visual_asset_path(*, content_hash: str, mime_type: str) -> str:
    """Return the content-addressed Prism path for a committed visual asset."""

    match = _SHA256_PATTERN.fullmatch(str(content_hash or "").strip().lower())
    if match is None:
        raise ValueError("visual asset requires a sha256 content hash")
    suffix = _VISUAL_SUFFIX_BY_MIME.get(str(mime_type or "").strip().lower())
    if suffix is None:
        raise ValueError("visual asset MIME type cannot be inserted into Prism")
    return f"figures/{match.group(1)}{suffix}"


def canonical_workspace_asset_url(*, workspace_id: str, storage_path: str) -> str:
    """Return the authenticated workspace URL for one canonical asset path."""

    normalized_workspace_id = str(workspace_id or "").strip()
    raw_path = str(storage_path or "").strip().replace("\\", "/")
    path = PurePosixPath(raw_path)
    if not normalized_workspace_id or not raw_path or path.is_absolute():
        raise ValueError("workspace asset URL requires a workspace-relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("workspace asset URL contains an unsafe path")
    return (
        f"/api/workspaces/{quote(normalized_workspace_id, safe='')}/files/"
        f"{quote(path.as_posix(), safe='/')}"
    )


def insert_after_prism_selection(
    *,
    content: str,
    selection_byte_range: tuple[int, int],
    selection_hash: str,
    insertion: str,
) -> str:
    """Apply one reviewed insertion while preserving the document newline style."""

    prefix, selection, suffix = split_utf8_selection(
        content,
        selection_byte_range,
    )
    if prism_selection_hash(selection) != selection_hash:
        raise ValueError("Prism selection changed before insertion")
    newline = _preferred_newline(content)
    selected_prefix = f"{prefix}{selection}"
    before = (
        ""
        if selected_prefix.endswith(newline * 2)
        else newline
        if selected_prefix.endswith(newline)
        else newline * 2
    )
    after = (
        ""
        if suffix.startswith(newline * 2)
        else newline
        if suffix.startswith(newline)
        else newline * 2
    )
    return f"{selected_prefix}{before}{insertion}{after}{suffix}"


def _preferred_newline(content: str) -> str:
    match = re.search(r"\r\n|\n|\r", content)
    return match.group(0) if match is not None else "\n"


__all__ = [
    "canonical_visual_asset_path",
    "canonical_workspace_asset_url",
    "insert_after_prism_selection",
]
