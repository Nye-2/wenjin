"""Canonical filesystem layout for one Wenjin workspace sandbox."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = "/workspace"
WORKSPACE_LAYOUT_SCHEMA = "wenjin.workspace_sandbox.layout.v1"
WORKSPACE_LAYOUT_VERSION = 1
WORKSPACE_MANIFEST_RELATIVE_PATH = ".wenjin/manifest.json"
WORKSPACE_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_MANIFEST_RELATIVE_PATH}"
WORKSPACE_HARNESS_OUTPUTS_RELATIVE_PATH = "outputs/harness"
WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT = f"{WORKSPACE_ROOT}/{WORKSPACE_HARNESS_OUTPUTS_RELATIVE_PATH}"

WORKSPACE_STANDARD_DIRS = (
    "main",
    "datasets",
    "scripts",
    "outputs",
    "reports",
    "tmp",
    ".wenjin/env",
    ".wenjin/cache",
)

WORKSPACE_PROTECTED_PATHS = (
    ".git/**",
    ".env",
    "*.pem",
    "*.key",
    ".wenjin/env/**",
    ".wenjin/cache/**",
    WORKSPACE_MANIFEST_RELATIVE_PATH,
)

WORKSPACE_INTERNAL_PATHS = (
    f"{WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT}/**",
)

_DIRECTORY_CONTRACTS: dict[str, dict[str, Any]] = {
    "main": {
        "virtual_path": f"{WORKSPACE_ROOT}/main",
        "purpose": "primary_project",
        "review_surface": "workspace",
    },
    "datasets": {
        "virtual_path": f"{WORKSPACE_ROOT}/datasets",
        "purpose": "datasets_and_inputs",
        "review_surface": "workspace",
    },
    "scripts": {
        "virtual_path": f"{WORKSPACE_ROOT}/scripts",
        "purpose": "reusable_experiment_scripts",
        "review_surface": "workspace",
    },
    "outputs": {
        "virtual_path": f"{WORKSPACE_ROOT}/outputs",
        "purpose": "generated_artifacts",
        "review_surface": "artifact",
    },
    "reports": {
        "virtual_path": f"{WORKSPACE_ROOT}/reports",
        "purpose": "analysis_reports",
        "review_surface": "artifact",
    },
    "tmp": {
        "virtual_path": f"{WORKSPACE_ROOT}/tmp",
        "purpose": "ephemeral_scratch",
        "review_surface": "hidden",
    },
    ".wenjin/env": {
        "virtual_path": f"{WORKSPACE_ROOT}/.wenjin/env",
        "purpose": "managed_runtime_environment",
        "review_surface": "hidden",
    },
    ".wenjin/cache": {
        "virtual_path": f"{WORKSPACE_ROOT}/.wenjin/cache",
        "purpose": "managed_runtime_cache",
        "review_surface": "hidden",
    },
}


def ensure_workspace_sandbox_layout(
    workspace_path: str | Path,
    *,
    workspace_id: str | None = None,
    sandbox_id: str | None = None,
    workspace_type: str | None = None,
) -> dict[str, Any]:
    """Create the canonical workspace sandbox tree and persist its manifest."""

    root = Path(workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    for relative_path in WORKSPACE_STANDARD_DIRS:
        (root / relative_path).mkdir(parents=True, exist_ok=True)

    manifest = build_workspace_sandbox_manifest(
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
        workspace_type=workspace_type,
    )
    manifest_path = root / WORKSPACE_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_text = json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != manifest_text:
        manifest_path.write_text(manifest_text, encoding="utf-8")
    return manifest


def build_workspace_sandbox_manifest(
    *,
    workspace_id: str | None = None,
    sandbox_id: str | None = None,
    workspace_type: str | None = None,
) -> dict[str, Any]:
    """Return the machine-readable sandbox layout contract."""

    return {
        "schema": WORKSPACE_LAYOUT_SCHEMA,
        "version": WORKSPACE_LAYOUT_VERSION,
        "virtual_root": WORKSPACE_ROOT,
        "workspace_id": workspace_id,
        "sandbox_id": sandbox_id,
        "workspace_type": workspace_type,
        "manifest_path": WORKSPACE_MANIFEST_VIRTUAL_PATH,
        "directories": deepcopy(_DIRECTORY_CONTRACTS),
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "artifact_roots": {
            "outputs": f"{WORKSPACE_ROOT}/outputs",
            "reports": f"{WORKSPACE_ROOT}/reports",
        },
        "runtime_roots": {
            "python_env": f"{WORKSPACE_ROOT}/.wenjin/env",
            "cache": f"{WORKSPACE_ROOT}/.wenjin/cache",
        },
        "internal_paths": list(WORKSPACE_INTERNAL_PATHS),
    }


def build_agent_workspace_contract(
    *,
    workspace_id: str | None = None,
    workspace_type: str | None = None,
) -> dict[str, Any]:
    """Return the compact sandbox filesystem contract shown to tool-using agents."""

    manifest = build_workspace_sandbox_manifest(
        workspace_id=workspace_id,
        workspace_type=workspace_type,
    )
    directories = {
        name: {
            "path": contract["virtual_path"],
            "purpose": contract["purpose"],
            "review_surface": contract["review_surface"],
        }
        for name, contract in manifest["directories"].items()
    }
    return {
        "schema": WORKSPACE_LAYOUT_SCHEMA,
        "version": WORKSPACE_LAYOUT_VERSION,
        "virtual_root": WORKSPACE_ROOT,
        "workspace_id": workspace_id,
        "workspace_type": workspace_type,
        "directories": directories,
        "artifact_roots": manifest["artifact_roots"],
        "runtime_roots": manifest["runtime_roots"],
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "internal_paths": list(WORKSPACE_INTERNAL_PATHS),
        "rules": [
            "Use only /workspace virtual paths when calling sandbox tools.",
            "Write reusable scripts under /workspace/scripts.",
            "Write user-reviewable generated files under /workspace/outputs or /workspace/reports.",
            "Use /workspace/tmp only for scratch data that should not be surfaced by default.",
            "Do not read or write protected paths.",
            "Do not register or cite /workspace/outputs/harness/** as user-facing artifacts.",
        ],
    }


def workspace_virtual_path(relative_path: str) -> str:
    """Resolve a relative workspace path into the canonical virtual namespace."""

    normalized = str(relative_path or "").strip().strip("/")
    if not normalized:
        return WORKSPACE_ROOT
    return f"{WORKSPACE_ROOT}/{normalized}"
