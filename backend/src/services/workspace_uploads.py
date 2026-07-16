"""Shared helpers for persisting user-uploaded workspace files."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from src.services.path_safety import normalize_path_component

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_UPLOAD_ROOT = Path(".wenjin/workspace_uploads")
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_TEXT_PREVIEW_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
}
_TEXT_PREVIEW_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".tex",
    ".bib",
    ".py",
    ".r",
}
_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:;|\n| and )\s*", re.IGNORECASE)


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


def is_image_upload(filename: str | None, content_type: str | None) -> bool:
    """Return whether the uploaded file should be treated as an image."""
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type.startswith("image/"):
        return True
    return Path(str(filename or "")).suffix.lower() in _IMAGE_SUFFIXES


def workspace_upload_dir(
    workspace_id: str,
    bucket: str,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> Path:
    """Resolve a workspace-scoped upload directory."""
    workspace_component = normalize_path_component(workspace_id)
    bucket_component = normalize_path_component(bucket)
    target = Path(root) / workspace_component / bucket_component
    target.mkdir(parents=True, exist_ok=True)
    return target


def workspace_upload_root(
    workspace_id: str,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> Path:
    """Resolve the workspace-level canonical upload root."""
    workspace_component = normalize_path_component(workspace_id)
    return Path(root) / workspace_component


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _is_workspace_root_prefixed_relative_path(
    candidate: Path,
    *,
    root: Path,
    workspace_id: str,
) -> bool:
    if candidate.is_absolute():
        return False
    root_path = Path(root)
    if root_path.is_absolute():
        return False
    try:
        candidate.relative_to(root_path / normalize_path_component(workspace_id))
        return True
    except ValueError:
        return False


def resolve_workspace_upload_relative_path(
    workspace_id: str,
    relative_path: str,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> Path:
    """Resolve a workspace upload path relative to the workspace upload root."""
    workspace_root = workspace_upload_root(workspace_id, root=root).resolve()
    normalized_relative = str(relative_path or "").strip().lstrip("/")
    if not normalized_relative:
        raise ValueError("Missing file path")

    candidate = (workspace_root / normalized_relative).resolve()
    if not _is_within_root(candidate, workspace_root):
        raise ValueError("File path escapes workspace uploads root")
    return candidate


def resolve_workspace_upload_stored_path(
    workspace_id: str,
    stored_path: str,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
    allow_root_prefixed_relative: bool = False,
) -> Path:
    """Resolve a stored workspace upload path and verify it belongs to the workspace."""
    workspace_root = workspace_upload_root(workspace_id, root=root).resolve()
    normalized_path = str(stored_path or "").strip()
    if not normalized_path:
        raise ValueError("Missing file path")

    raw_path = Path(normalized_path)
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
        if (
            allow_root_prefixed_relative
            and not _is_within_root(candidate, workspace_root)
            and normalized_path.startswith("/")
            and not candidate.exists()
        ):
            candidate = (workspace_root / normalized_path.lstrip("/")).resolve()
    else:
        if _is_workspace_root_prefixed_relative_path(
            raw_path,
            root=Path(root),
            workspace_id=workspace_id,
        ):
            raise ValueError("Stored file path must be workspace-relative")
        candidate = (workspace_root / normalized_path.lstrip("/")).resolve()
    if not _is_within_root(candidate, workspace_root):
        raise ValueError("File path escapes workspace uploads root")
    return candidate


def workspace_upload_public_url(
    workspace_id: str,
    stored_path: str | Path | None,
    *,
    root: Path = DEFAULT_WORKSPACE_UPLOAD_ROOT,
) -> str | None:
    """Map a persisted workspace upload path to its canonical API URL."""
    if stored_path is None:
        return None

    actual_path = resolve_workspace_upload_stored_path(
        workspace_id,
        str(stored_path),
        root=root,
        allow_root_prefixed_relative=True,
    )
    relative = actual_path.relative_to(
        workspace_upload_root(workspace_id, root=root).resolve()
    ).as_posix()
    return f"/api/workspaces/{workspace_id}/files/{quote(relative)}"


def _normalize_text_preview(text: str, *, max_chars: int) -> str | None:
    preview = " ".join(text.split())
    if not preview:
        return None
    return preview[:max_chars]


def _is_text_like_upload(filename: str | None, content_type: str | None) -> bool:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    suffix = Path(str(filename or "")).suffix.lower()
    return (
        normalized_content_type.startswith("text/")
        or normalized_content_type in _TEXT_PREVIEW_CONTENT_TYPES
        or suffix in _TEXT_PREVIEW_SUFFIXES
    )


def _split_document_authors(raw: str) -> list[str]:
    stripped = str(raw or "").strip()
    if not stripped:
        return []

    if ";" in stripped or "\n" in stripped or " and " in stripped.lower():
        candidates = _AUTHOR_SPLIT_RE.split(stripped)
    else:
        candidates = [stripped]

    authors: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip(" ,;")
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        authors.append(normalized)
    return authors


def extract_document_preview(
    filename: str | None,
    content_type: str | None,
    *,
    content: bytes | None = None,
    file_path: str | Path | None = None,
    max_chars: int = 1200,
    max_pages: int = 2,
) -> dict[str, object]:
    """Extract lightweight preview metadata from an uploaded document.

    Returns a dict with keys:
    - ``title``: document title if detected
    - ``authors``: list of author names
    - ``page_count``: PDF page count when applicable
    - ``text_preview``: compact text preview for text/PDF uploads
    """
    preview: dict[str, object] = {
        "title": None,
        "authors": [],
        "page_count": None,
        "text_preview": None,
    }

    if is_pdf_upload(filename, content_type):
        try:
            import fitz  # PyMuPDF

            if content is not None:
                doc = fitz.open(stream=content, filetype="pdf")
            elif file_path is not None:
                doc = fitz.open(str(file_path))
            else:
                return preview

            with doc:
                metadata = doc.metadata or {}
                preview["title"] = (metadata.get("title") or "").strip() or None
                preview["authors"] = _split_document_authors(
                    metadata.get("author") or ""
                )
                preview["page_count"] = doc.page_count
                text_parts: list[str] = []
                for page_index in range(min(doc.page_count, max_pages)):
                    page = doc.load_page(page_index)
                    text_parts.append(page.get_text())
                preview["text_preview"] = _normalize_text_preview(
                    "\n".join(text_parts),
                    max_chars=max_chars,
                )
        except Exception:
            logger.warning(
                "Failed to extract PDF preview metadata: filename=%s content_type=%s",
                filename,
                content_type,
                exc_info=True,
            )
            return preview

        return preview

    if content is not None and _is_text_like_upload(filename, content_type):
        preview["text_preview"] = _normalize_text_preview(
            content.decode("utf-8", errors="replace"),
            max_chars=max_chars,
        )

    return preview


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
