"""Shared helpers for persisting user-uploaded workspace files."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.execution.path_utils import normalize_thread_id

DEFAULT_WORKSPACE_UPLOAD_ROOT = Path(".academiagpt/workspace_uploads")
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def sanitize_upload_filename(filename: str | None) -> str:
    """Normalize an uploaded filename into a safe single path component."""
    candidate = Path(str(filename or "").strip()).name
    if not candidate or candidate in {".", ".."}:
        raise ValueError("Invalid filename")
    return candidate


def next_available_path(directory: Path, filename: str) -> Path:
    """Allocate a non-conflicting target path inside ``directory``."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def is_pdf_upload(filename: str | None, content_type: str | None) -> bool:
    """Return whether the uploaded file should be treated as a PDF."""
    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type in _PDF_CONTENT_TYPES:
        return True
    return Path(str(filename or "")).suffix.lower() == ".pdf"


def workspace_upload_dir(
    workspace_id: str,
    bucket: str,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> Path:
    """Resolve a workspace-scoped upload directory."""
    workspace_component = normalize_thread_id(workspace_id)
    bucket_component = normalize_thread_id(bucket)
    target = Path(root) / workspace_component / bucket_component
    target.mkdir(parents=True, exist_ok=True)
    return target


def persist_workspace_upload(
    *,
    workspace_id: str,
    bucket: str,
    filename: str,
    content: bytes | None = None,
    source_path: Path | None = None,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> Path:
    """Persist an upload into the canonical workspace uploads area."""
    if (content is None) == (source_path is None):
        raise ValueError("Provide exactly one of content or source_path")

    safe_filename = sanitize_upload_filename(filename)
    target_dir = workspace_upload_dir(workspace_id, bucket, root=root)
    target_path = next_available_path(target_dir, safe_filename)

    if source_path is not None:
        shutil.copy2(source_path, target_path)
    else:
        target_path.write_bytes(content or b"")

    return target_path
