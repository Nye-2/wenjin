"""Canonical public virtual-path contract for Sandbox vNext.

Host layout, receipts, manifests and output refs are intentionally absent from
this module.  Trusted control state lives in :mod:`src.sandbox.storage` and is
never represented as a writable ``/workspace`` path.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Literal

from src.sandbox.security import (
    ARTIFACT_ROOTS,
    PUBLIC_WORKSPACE_DIRS,
    SandboxPathError,
    is_artifact_path,
    normalize_virtual_path,
    public_relative_path,
)

WORKSPACE_ROOT = "/workspace"
WORKSPACE_LAYOUT_SCHEMA = "wenjin.sandbox.public_workspace.v2"
WORKSPACE_LAYOUT_VERSION = 2
WORKSPACE_STANDARD_DIRS = (*PUBLIC_WORKSPACE_DIRS, "tmp")
WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT = "/workspace/tmp/tasks"

WORKSPACE_PROTECTED_PATHS = (
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".wenjin/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
)

WORKSPACE_ARTIFACT_ROOTS = tuple(
    {
        "name": root,
        "virtual_path": f"/workspace/{root}",
        "artifact_kind": "sandbox_output" if root == "outputs" else "sandbox_report",
    }
    for root in ARTIFACT_ROOTS
)

WORKSPACE_PATH_CLASSES = {
    "workspace": ["/workspace/main"],
    "datasets": ["/workspace/datasets"],
    "scripts": ["/workspace/scripts"],
    "artifacts": ["/workspace/outputs", "/workspace/reports"],
    "scratch": ["/workspace/tmp"],
    "protected": list(WORKSPACE_PROTECTED_PATHS),
}

WORKSPACE_SEARCH_IGNORED_NAMES = (
    ".git",
    ".hg",
    ".svn",
    ".wenjin",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".next",
    ".nuxt",
    ".turbo",
)

WorkspacePathClass = Literal["protected", "artifact", "hidden", "workspace"]
_SCRATCH_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def workspace_virtual_path(relative_path: str) -> str:
    relative = PurePosixPath(str(relative_path or "").strip().lstrip("/"))
    if not relative.parts or ".." in relative.parts:
        raise ValueError("workspace relative path is invalid")
    return normalize_workspace_virtual_path(f"{WORKSPACE_ROOT}/{relative.as_posix()}")


def normalize_workspace_virtual_path(path: str) -> str:
    try:
        return normalize_virtual_path(path)
    except SandboxPathError as exc:
        raise ValueError(str(exc)) from exc


def workspace_relative_path(path: str) -> str:
    normalized = normalize_workspace_virtual_path(path)
    if normalized == WORKSPACE_ROOT:
        return ""
    return normalized.removeprefix(f"{WORKSPACE_ROOT}/")


def workspace_task_scratch_path(
    *,
    mission_id: str,
    mission_item_seq: int | None = None,
    subagent_id: str | None = None,
) -> str:
    mission = _safe_segment(mission_id, default="mission")
    owner = _safe_segment(subagent_id, default="") or (f"item-{mission_item_seq}" if mission_item_seq is not None else "mission")
    return f"{WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT}/{mission}/{owner}"


def build_agent_workspace_contract() -> dict[str, object]:
    return {
        "schema": WORKSPACE_LAYOUT_SCHEMA,
        "version": WORKSPACE_LAYOUT_VERSION,
        "root": WORKSPACE_ROOT,
        "public_directories": [{"name": name, "virtual_path": f"{WORKSPACE_ROOT}/{name}"} for name in WORKSPACE_STANDARD_DIRS],
        "artifact_roots": list(WORKSPACE_ARTIFACT_ROOTS),
        "default_network_profile": "none",
        "typed_operations": [
            "sandbox.run_python",
            "sandbox.run_notebook",
            "sandbox.smoke_check",
            "sandbox.install_dependencies",
            "sandbox.register_dataset",
            "sandbox.register_artifact",
            "sandbox.read_output_ref",
        ],
        "rules": [
            "Control state and output refs are not public workspace paths.",
            "Datasets are read-only during compute operations.",
            "Only manifest-backed files under outputs/reports may enter review.",
            "Existing file writes require the current base content hash.",
        ],
    }


def build_workspace_task_contract(
    *,
    mission_id: str,
    mission_item_seq: int | None = None,
    subagent_id: str | None = None,
) -> dict[str, object]:
    scratch = workspace_task_scratch_path(
        mission_id=mission_id,
        mission_item_seq=mission_item_seq,
        subagent_id=subagent_id,
    )
    return {
        "schema": "wenjin.sandbox.task_contract.v2",
        "mission_id": mission_id,
        "mission_item_seq": mission_item_seq,
        "subagent_id": subagent_id,
        "scratch_path": scratch,
        "reviewable_artifact_roots": ["/workspace/outputs", "/workspace/reports"],
        "read_output_ref_tool": "sandbox.read_output_ref",
    }


def is_workspace_protected_path(path: str, *, protected_paths: tuple[str, ...] | None = None) -> bool:
    try:
        relative = workspace_relative_path(path)
    except ValueError:
        return True
    patterns = protected_paths or WORKSPACE_PROTECTED_PATHS
    return any(_matches(relative, pattern) for pattern in patterns)


def is_workspace_internal_path(path: str) -> bool:
    """No public internal path exists; protected control-like names stay denied."""

    try:
        relative = public_relative_path(path, allow_root=True)
    except SandboxPathError:
        return True
    return any(part in {".wenjin", ".internal"} for part in relative.parts)


def is_workspace_search_ignored_path(path: str) -> bool:
    try:
        relative = public_relative_path(path, allow_root=True)
    except SandboxPathError:
        return True
    return any(part in WORKSPACE_SEARCH_IGNORED_NAMES for part in relative.parts)


def workspace_artifact_root_for_path(path: str) -> dict[str, str] | None:
    if not is_artifact_path(path):
        return None
    normalized = normalize_workspace_virtual_path(path)
    for root in WORKSPACE_ARTIFACT_ROOTS:
        virtual = root["virtual_path"]
        if normalized == virtual or normalized.startswith(f"{virtual}/"):
            return dict(root)
    return None


def is_user_reviewable_workspace_artifact_path(path: str) -> bool:
    return is_artifact_path(path) and not is_workspace_protected_path(path)


def is_user_editable_workspace_path(path: str) -> bool:
    try:
        relative = public_relative_path(path)
    except SandboxPathError:
        return False
    return bool(relative.parts and relative.parts[0] in PUBLIC_WORKSPACE_DIRS and not is_workspace_protected_path(path))


def classify_workspace_path(path: str) -> WorkspacePathClass:
    if is_workspace_protected_path(path) or is_workspace_internal_path(path):
        return "protected"
    relative = workspace_relative_path(path)
    if any(part.startswith(".") for part in PurePosixPath(relative).parts):
        return "hidden"
    if is_user_reviewable_workspace_artifact_path(path):
        return "artifact"
    return "workspace"


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(f"/{path}", pattern)


def _safe_segment(value: str | None, *, default: str) -> str:
    cleaned = _SCRATCH_SEGMENT_RE.sub("-", str(value or "").strip()).strip("-._")
    return (cleaned or default)[:100]
