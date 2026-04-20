"""Path helpers for persisted LaTeX projects."""

from __future__ import annotations

import os
from pathlib import Path

_RESERVED_PATH_SEGMENTS = frozenset({".git", ".compile", "__pycache__"})
_RESERVED_ROOT_FILES = frozenset({"project.json"})


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _resolve_configured_path(value: str, *, default: str) -> Path:
    raw = str(value or "").strip() or default
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = _backend_root() / path
    return path.resolve()


def get_latex_data_dir() -> Path:
    """Return configured LaTeX data root."""
    path = _resolve_configured_path(
        os.getenv("WENJIN_LATEX_DATA_DIR", ""),
        default=".wenjin/latex_projects",
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_latex_template_dir() -> Path:
    """Return configured LaTeX template root."""
    return _resolve_configured_path(
        os.getenv("WENJIN_LATEX_TEMPLATE_DIR", ""),
        default="../../WenjinPrism/templates",
    )


def project_root(project_id: str) -> Path:
    """Resolve a project's absolute root directory."""
    return (get_latex_data_dir() / str(project_id)).resolve()


def compile_runs_root(project_id: str) -> Path:
    """Resolve dedicated compile run root for a project."""
    path = (get_latex_data_dir() / "_compile_runs" / str(project_id)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_relative_path(path: str) -> str:
    """Normalize user provided relative path into POSIX form."""
    raw = str(path or "").replace("\\", "/")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("File path contains control characters")
    normalized = raw.strip().lstrip("/")
    if not normalized:
        raise ValueError("Missing file path")
    parts = [segment for segment in normalized.split("/") if segment]
    if any(segment in {".", ".."} for segment in parts):
        raise ValueError("File path contains invalid segments")
    return "/".join(parts)


def is_reserved_project_path(path: str) -> bool:
    """Return whether a user-provided relative path targets reserved internals."""
    normalized = str(path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return False
    parts = [segment.lower() for segment in normalized.split("/") if segment]
    if not parts:
        return False
    if parts[-1] in _RESERVED_ROOT_FILES:
        return True
    return any(segment in _RESERVED_PATH_SEGMENTS for segment in parts)


def resolve_project_relative(project_dir: Path, relative_path: str) -> Path:
    """Resolve and validate a path under a project root."""
    normalized = normalize_relative_path(relative_path)
    root = project_dir.resolve()
    candidate = (root / normalized).resolve()
    if not _is_within_root(candidate, root):
        raise ValueError("File path escapes project root")
    return candidate
