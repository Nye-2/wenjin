"""Canonical filesystem layout for one Wenjin workspace sandbox."""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Literal

WORKSPACE_ROOT = "/workspace"
WORKSPACE_LAYOUT_SCHEMA = "wenjin.workspace_sandbox.layout.v1"
WORKSPACE_LAYOUT_VERSION = 1
WORKSPACE_MANIFEST_RELATIVE_PATH = ".wenjin/manifest.json"
WORKSPACE_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_MANIFEST_RELATIVE_PATH}"
WORKSPACE_DATASET_PROVENANCE_SCHEMA = "wenjin.workspace_sandbox.dataset_provenance.v1"
WORKSPACE_DATASET_PROVENANCE_VERSION = 1
WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH = "datasets/manifest.json"
WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH}"
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

WORKSPACE_KEEP_FILE_DIRS = (
    "datasets",
    "scripts",
    "outputs",
    "reports",
)

WORKSPACE_MAIN_README_RELATIVE_PATH = "main/README.md"
WORKSPACE_DATASETS_README_RELATIVE_PATH = "datasets/README.md"
WORKSPACE_MAIN_README_TEXT = """# Wenjin Workspace

Use this sandbox as the persistent workspace filesystem for this research task.

- Put primary manuscript or project files under /workspace/main.
- Put datasets and uploaded inputs under /workspace/datasets.
- Put reusable experiment scripts under /workspace/scripts.
- Put generated figures, tables, metrics, and run outputs under /workspace/outputs.
- Put readable analysis notes and reports under /workspace/reports.
- Use /workspace/tmp only for scratch files that should not be surfaced by default.
- Do not read or write .wenjin, .git, .env, *.pem, or *.key paths.
"""

WORKSPACE_DATASETS_README_TEXT = """# Workspace Datasets

Use this directory for datasets and input materials that sandbox experiments may reuse.

- Put reusable data files under /workspace/datasets.
- Record dataset provenance in /workspace/datasets/manifest.json.
- Include source_id, content_hash, license, preparation notes, and source path when known.
- Do not store secrets, credentials, API keys, or private tokens here.
"""

WORKSPACE_DATASET_PROVENANCE_RULES = (
    "Record every reusable dataset or uploaded input used by sandbox experiments.",
    "Use /workspace/datasets virtual paths only.",
    "Keep secrets, API keys, credentials, and raw private tokens out of this manifest.",
    "Prefer stable source_id, content_hash, license, and preparation notes when known.",
)

DATASET_PROVENANCE_MANIFEST_ALLOWED_FIELDS = (
    "path",
    "source_id",
    "name",
    "title",
    "description",
    "format",
    "mime_type",
    "size_bytes",
    "content_hash",
    "license",
    "preparation",
    "created_at",
    "updated_at",
)

WORKSPACE_PROTECTED_PATHS = (
    ".git/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    ".wenjin/env/**",
    ".wenjin/cache/**",
    WORKSPACE_MANIFEST_RELATIVE_PATH,
)

WORKSPACE_INTERNAL_PATHS = (
    f"{WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT}/**",
)

WorkspacePathClass = Literal["protected", "internal", "artifact", "hidden", "workspace"]

WORKSPACE_ARTIFACT_ROOTS = (
    {
        "name": "outputs",
        "virtual_path": f"{WORKSPACE_ROOT}/outputs",
        "artifact_kind": "sandbox_output",
    },
    {
        "name": "reports",
        "virtual_path": f"{WORKSPACE_ROOT}/reports",
        "artifact_kind": "sandbox_report",
    },
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
    _ensure_workspace_guidance_files(root)

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


def _ensure_workspace_guidance_files(root: Path) -> None:
    readme_path = root / WORKSPACE_MAIN_README_RELATIVE_PATH
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    if not readme_path.exists():
        readme_path.write_text(WORKSPACE_MAIN_README_TEXT, encoding="utf-8")
    datasets_readme_path = root / WORKSPACE_DATASETS_README_RELATIVE_PATH
    datasets_readme_path.parent.mkdir(parents=True, exist_ok=True)
    if not datasets_readme_path.exists():
        datasets_readme_path.write_text(WORKSPACE_DATASETS_README_TEXT, encoding="utf-8")
    dataset_manifest_path = root / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH
    if not dataset_manifest_path.exists():
        dataset_manifest_path.write_text(
            json.dumps(build_dataset_provenance_manifest(), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    for relative_dir in WORKSPACE_KEEP_FILE_DIRS:
        keep_path = root / relative_dir / ".gitkeep"
        keep_path.parent.mkdir(parents=True, exist_ok=True)
        keep_path.touch(exist_ok=True)


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
        "datasets_manifest_path": WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
        "directories": deepcopy(_DIRECTORY_CONTRACTS),
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "artifact_roots": {
            root["name"]: root["virtual_path"]
            for root in WORKSPACE_ARTIFACT_ROOTS
        },
        "runtime_roots": {
            "python_env": f"{WORKSPACE_ROOT}/.wenjin/env",
            "cache": f"{WORKSPACE_ROOT}/.wenjin/cache",
        },
        "internal_paths": list(WORKSPACE_INTERNAL_PATHS),
    }


def build_dataset_provenance_manifest(*, datasets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return the default editable dataset provenance manifest."""

    return {
        "schema": WORKSPACE_DATASET_PROVENANCE_SCHEMA,
        "version": WORKSPACE_DATASET_PROVENANCE_VERSION,
        "root": f"{WORKSPACE_ROOT}/datasets",
        "datasets": list(datasets or []),
        "rules": list(WORKSPACE_DATASET_PROVENANCE_RULES),
    }


def merge_dataset_provenance_manifest(
    manifest: Mapping[str, Any] | None,
    datasets: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Merge safe runtime dataset refs into the editable dataset manifest.

    Existing manifest entries are user-authored state. They are preserved as-is
    and win over incoming DataService/runtime provenance for the same path.
    """

    merged = deepcopy(dict(manifest)) if isinstance(manifest, Mapping) else build_dataset_provenance_manifest()
    existing_datasets = merged.get("datasets")
    if not isinstance(existing_datasets, list):
        existing_datasets = []
    merged["datasets"] = existing_datasets

    existing_paths = {
        path
        for item in existing_datasets
        if isinstance(item, Mapping)
        for path in (_safe_dataset_manifest_path(item.get("path")),)
        if path
    }
    for raw_entry in datasets or []:
        entry = _safe_dataset_manifest_entry(raw_entry)
        if not entry:
            continue
        path = entry["path"]
        if path in existing_paths:
            continue
        existing_datasets.append(entry)
        existing_paths.add(path)
    return merged


def _safe_dataset_manifest_entry(raw_entry: Any) -> dict[str, Any] | None:
    if not isinstance(raw_entry, Mapping):
        return None
    path = _safe_dataset_manifest_path(raw_entry.get("path"))
    if not path:
        return None
    entry: dict[str, Any] = {"path": path}
    for key in DATASET_PROVENANCE_MANIFEST_ALLOWED_FIELDS:
        if key == "path" or key not in raw_entry:
            continue
        value = _safe_dataset_manifest_value(raw_entry.get(key))
        if value is not None:
            entry[key] = value
    return entry


def _safe_dataset_manifest_path(raw_path: Any) -> str | None:
    try:
        path = normalize_workspace_virtual_path(str(raw_path or ""))
    except ValueError:
        return None
    if not path.startswith(f"{WORKSPACE_ROOT}/datasets/"):
        return None
    if is_workspace_protected_path(path) or is_workspace_internal_path(path):
        return None
    relative = workspace_relative_path(path)
    if relative in {
        WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH,
        WORKSPACE_DATASETS_README_RELATIVE_PATH,
        "datasets/.gitkeep",
    }:
        return None
    return path


def _safe_dataset_manifest_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\x00" in text or _contains_workspace_secret_ref(text) or _contains_host_path_ref(text):
        return None
    if len(text) > 1000:
        return text[:1000]
    return text


def _contains_workspace_secret_ref(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            f"{WORKSPACE_ROOT}/.wenjin",
            f"{WORKSPACE_ROOT}/outputs/harness",
            f"{WORKSPACE_ROOT}/.env",
            "/.env",
            ".pem",
            ".key",
        )
    )


def _contains_host_path_ref(text: str) -> bool:
    for token in text.translate(str.maketrans({"(": " ", ")": " ", ",": " ", ";": " "})).split():
        if token.startswith("/") and not token.startswith(f"{WORKSPACE_ROOT}/"):
            return True
    return False


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
        "datasets_manifest_path": WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
        "runtime_roots": manifest["runtime_roots"],
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "internal_paths": list(WORKSPACE_INTERNAL_PATHS),
        "rules": [
            "Use only /workspace virtual paths when calling sandbox tools.",
            "Record reusable dataset provenance in /workspace/datasets/manifest.json.",
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


def normalize_workspace_virtual_path(path: str) -> str:
    """Normalize a path into the canonical `/workspace` virtual namespace.

    Providers may return physical paths that contain the mounted `/workspace`
    segment. Harness-facing code should convert those back to virtual paths
    before policy, review, or artifact decisions.
    """

    text = str(path or "").strip()
    if "\x00" in text:
        raise ValueError("workspace path contains null byte")
    if text == WORKSPACE_ROOT:
        normalized = text
    elif text.startswith(f"{WORKSPACE_ROOT}/"):
        normalized = text
    elif f"{WORKSPACE_ROOT}/" in text:
        normalized = f"{WORKSPACE_ROOT}/{text.split(f'{WORKSPACE_ROOT}/', 1)[1]}"
    else:
        raise ValueError(f"path must be under {WORKSPACE_ROOT}")

    pure = PurePosixPath(normalized)
    if ".." in pure.parts:
        raise ValueError("workspace path traversal is not allowed")
    return pure.as_posix()


def workspace_relative_path(path: str) -> str:
    """Return the path relative to `/workspace` after validation."""

    normalized = normalize_workspace_virtual_path(path)
    if normalized == WORKSPACE_ROOT:
        return ""
    return normalized.removeprefix(WORKSPACE_ROOT).lstrip("/")


def is_workspace_protected_path(
    path: str,
    *,
    protected_paths: tuple[str, ...] = WORKSPACE_PROTECTED_PATHS,
) -> bool:
    """Return whether a workspace path is protected from model tools."""

    try:
        relative = workspace_relative_path(path)
    except ValueError:
        return False
    for pattern in protected_paths:
        if _matches_workspace_pattern(relative, pattern):
            return True
    return False


def is_workspace_internal_path(path: str) -> bool:
    """Return whether a path is internal harness/runtime state."""

    try:
        normalized = normalize_workspace_virtual_path(path)
    except ValueError:
        return False
    return any(_matches_workspace_pattern(normalized, pattern) for pattern in WORKSPACE_INTERNAL_PATHS)


def workspace_artifact_root_for_path(path: str) -> dict[str, str] | None:
    """Return the user-reviewable artifact root metadata for a workspace path."""

    if is_workspace_internal_path(path):
        return None
    try:
        normalized = normalize_workspace_virtual_path(path)
    except ValueError:
        return None
    for root in WORKSPACE_ARTIFACT_ROOTS:
        root_path = root["virtual_path"]
        if normalized.startswith(f"{root_path}/"):
            return dict(root)
    return None


def is_user_reviewable_workspace_artifact_path(path: str) -> bool:
    """Return whether a sandbox path can be staged as a user-reviewable artifact."""

    return workspace_artifact_root_for_path(path) is not None


def classify_workspace_path(path: str) -> WorkspacePathClass:
    """Classify a workspace path for harness policy and UI projection."""

    normalized = normalize_workspace_virtual_path(path)
    if is_workspace_protected_path(normalized):
        return "protected"
    if is_workspace_internal_path(normalized):
        return "internal"
    if workspace_artifact_root_for_path(normalized) is not None:
        return "artifact"
    relative = workspace_relative_path(normalized)
    for directory, contract in _DIRECTORY_CONTRACTS.items():
        if relative == directory or relative.startswith(f"{directory}/"):
            surface = str(contract.get("review_surface") or "workspace")
            return "hidden" if surface == "hidden" else "workspace"
    return "workspace"


def _matches_workspace_pattern(path: str, pattern: str) -> bool:
    text = str(path).strip("/")
    pattern_text = str(pattern).strip("/")
    if fnmatch.fnmatch(text, pattern_text):
        return True
    if pattern_text.endswith("/**"):
        base = pattern_text.removesuffix("/**")
        return text == base or text.startswith(f"{base}/")
    return False
