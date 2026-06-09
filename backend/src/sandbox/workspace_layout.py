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
WORKSPACE_TYPE_PROFILE_SCHEMA = "wenjin.workspace_sandbox.type_profile.v1"
WORKSPACE_MANIFEST_RELATIVE_PATH = ".wenjin/manifest.json"
WORKSPACE_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_MANIFEST_RELATIVE_PATH}"
WORKSPACE_DATASET_PROVENANCE_SCHEMA = "wenjin.workspace_sandbox.dataset_provenance.v1"
WORKSPACE_DATASET_PROVENANCE_VERSION = 1
WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH = "datasets/manifest.json"
WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH}"
WORKSPACE_ARTIFACT_MANIFEST_SCHEMA = "wenjin.workspace_sandbox.artifact_manifest.v1"
WORKSPACE_ARTIFACT_MANIFEST_VERSION = 1
WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH = "reports/artifacts.json"
WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH = f"{WORKSPACE_ROOT}/{WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH}"
WORKSPACE_TASK_SCRATCH_RELATIVE_ROOT = "tmp/tasks"
WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT = f"{WORKSPACE_ROOT}/{WORKSPACE_TASK_SCRATCH_RELATIVE_ROOT}"
WORKSPACE_HARNESS_INTERNAL_RELATIVE_ROOT = f"{WORKSPACE_TASK_SCRATCH_RELATIVE_ROOT}/.harness"
WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT = f"{WORKSPACE_ROOT}/{WORKSPACE_HARNESS_INTERNAL_RELATIVE_ROOT}"
WORKSPACE_HARNESS_OUTPUTS_RELATIVE_PATH = f"{WORKSPACE_HARNESS_INTERNAL_RELATIVE_ROOT}/outputs"
WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT = f"{WORKSPACE_ROOT}/{WORKSPACE_HARNESS_OUTPUTS_RELATIVE_PATH}"

WORKSPACE_STANDARD_DIRS = (
    "main",
    "datasets",
    "scripts",
    "outputs",
    "reports",
    "tmp",
    WORKSPACE_TASK_SCRATCH_RELATIVE_ROOT,
    WORKSPACE_HARNESS_OUTPUTS_RELATIVE_PATH,
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
WORKSPACE_OUTPUTS_README_RELATIVE_PATH = "outputs/README.md"
WORKSPACE_REPORTS_README_RELATIVE_PATH = "reports/README.md"
WORKSPACE_MAIN_README_TEXT = """# Wenjin Workspace

Use this sandbox as the persistent workspace filesystem for this research task.

- Put primary manuscript or project files under /workspace/main.
- Put datasets and uploaded inputs under /workspace/datasets.
- Put reusable experiment scripts under /workspace/scripts.
- Put generated figures, tables, metrics, and run outputs under /workspace/outputs.
- Put readable analysis notes and reports under /workspace/reports.
- Use /workspace/tmp only for scratch files that should not be surfaced by default.
- Internal tool output refs live under /workspace/tmp/tasks/.harness and are read-only by explicit ref.
- Do not read or write .wenjin, .git, .env, *.pem, or *.key paths.
"""

WORKSPACE_DATASETS_README_TEXT = """# Workspace Datasets

Use this directory for datasets and input materials that sandbox experiments may reuse.

- Put reusable data files under /workspace/datasets.
- Record dataset provenance in /workspace/datasets/manifest.json.
- Include source_id, content_hash, license, preparation notes, and source path when known.
- Do not store secrets, credentials, API keys, or private tokens here.
"""

WORKSPACE_OUTPUTS_README_TEXT = """# Workspace Outputs

Use this directory for generated figures, tables, metrics, and other files that may be reviewed by the user.

- Put reviewable generated files directly under /workspace/outputs or a clear subdirectory.
- Do not write model-visible debug dumps under /workspace/outputs.
- Do not register internal tool refs as user-facing artifacts.
- Keep temporary scratch data under /workspace/tmp instead.
"""

WORKSPACE_REPORTS_README_TEXT = """# Workspace Reports

Use this directory for readable reports, audits, revision plans, and experiment notes.

- Put user-facing Markdown or text reports under /workspace/reports.
- Record artifact metadata in /workspace/reports/artifacts.json when known.
- Do not store secrets, credentials, API keys, or private tokens here.
- Keep raw stdout, stderr, and tool dumps under /workspace/tmp/tasks/.harness only.
"""

WORKSPACE_GUIDANCE_RELATIVE_PATHS = (
    WORKSPACE_MAIN_README_RELATIVE_PATH,
    WORKSPACE_DATASETS_README_RELATIVE_PATH,
    WORKSPACE_OUTPUTS_README_RELATIVE_PATH,
    WORKSPACE_REPORTS_README_RELATIVE_PATH,
    WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH,
    WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH,
    "datasets/.gitkeep",
    "scripts/.gitkeep",
    "outputs/.gitkeep",
    "reports/.gitkeep",
)

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

WORKSPACE_ARTIFACT_MANIFEST_RULES = (
    "Record user-reviewable generated artifacts under /workspace/outputs or /workspace/reports.",
    "Use /workspace virtual paths only.",
    "Do not register internal refs or protected files.",
    "Prefer title, artifact_kind, content_hash, source_script, dataset_paths, and review notes when known.",
)

ARTIFACT_MANIFEST_ALLOWED_FIELDS = (
    "path",
    "title",
    "description",
    "artifact_kind",
    "mime_type",
    "size_bytes",
    "content_hash",
    "source_script",
    "dataset_paths",
    "notes",
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
    ".wenjin/**",
)

WORKSPACE_INTERNAL_PATHS = (
    f"{WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT}/**",
)

WORKSPACE_PATH_CLASSES = {
    "workspace": [f"{WORKSPACE_ROOT}/main"],
    "datasets": [f"{WORKSPACE_ROOT}/datasets"],
    "scripts": [f"{WORKSPACE_ROOT}/scripts"],
    "artifacts": [f"{WORKSPACE_ROOT}/outputs", f"{WORKSPACE_ROOT}/reports"],
    "scratch": [f"{WORKSPACE_ROOT}/tmp"],
    "task_scratch": [WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT],
    "runtime": [f"{WORKSPACE_ROOT}/.wenjin/env", f"{WORKSPACE_ROOT}/.wenjin/cache"],
    "protected": list(WORKSPACE_PROTECTED_PATHS),
    "internal": list(WORKSPACE_INTERNAL_PATHS),
    "guidance": [f"{WORKSPACE_ROOT}/{path}" for path in WORKSPACE_GUIDANCE_RELATIVE_PATHS],
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
    ".DS_Store",
    "Thumbs.db",
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

_GENERIC_WORKSPACE_PROFILE: dict[str, Any] = {
    "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
    "workspace_type": "generic",
    "label": "General research workspace",
    "primary_files": [
        f"{WORKSPACE_ROOT}/main/README.md",
    ],
    "script_paths": [
        f"{WORKSPACE_ROOT}/scripts/analysis.py",
        f"{WORKSPACE_ROOT}/scripts/reproduce.py",
    ],
    "output_paths": [
        f"{WORKSPACE_ROOT}/outputs",
    ],
    "report_paths": [
        f"{WORKSPACE_ROOT}/reports/summary.md",
    ],
    "rules": [
        "Keep primary project files under /workspace/main.",
        "Keep reusable experiments under /workspace/scripts and generated outputs under /workspace/outputs.",
        "Keep readable notes, audits, and delivery reports under /workspace/reports.",
        "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
    ],
}

_WORKSPACE_TYPE_PROFILES: dict[str, dict[str, Any]] = {
    "thesis": {
        "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
        "workspace_type": "thesis",
        "label": "Thesis workspace",
        "primary_files": [
            f"{WORKSPACE_ROOT}/main/main.tex",
            f"{WORKSPACE_ROOT}/main/refs.bib",
            f"{WORKSPACE_ROOT}/main/README.md",
        ],
        "script_paths": [
            f"{WORKSPACE_ROOT}/scripts/analysis.py",
            f"{WORKSPACE_ROOT}/scripts/reproduce.py",
        ],
        "output_paths": [
            f"{WORKSPACE_ROOT}/outputs/figures",
            f"{WORKSPACE_ROOT}/outputs/tables",
            f"{WORKSPACE_ROOT}/outputs/metrics",
        ],
        "report_paths": [
            f"{WORKSPACE_ROOT}/reports/chapter-review.md",
            f"{WORKSPACE_ROOT}/reports/experiment-report.md",
            f"{WORKSPACE_ROOT}/reports/revision-plan.md",
        ],
        "rules": [
            "Keep thesis-facing files under /workspace/main.",
            "Keep reusable experiments under /workspace/scripts and generated figures/tables under /workspace/outputs.",
            "Keep chapter audits, experiment reports, and revision plans under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    },
    "sci": {
        "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
        "workspace_type": "sci",
        "label": "SCI paper workspace",
        "primary_files": [
            f"{WORKSPACE_ROOT}/main/main.tex",
            f"{WORKSPACE_ROOT}/main/refs.bib",
            f"{WORKSPACE_ROOT}/main/README.md",
        ],
        "script_paths": [
            f"{WORKSPACE_ROOT}/scripts/analysis.py",
            f"{WORKSPACE_ROOT}/scripts/reproduce.py",
        ],
        "output_paths": [
            f"{WORKSPACE_ROOT}/outputs/figures",
            f"{WORKSPACE_ROOT}/outputs/tables",
            f"{WORKSPACE_ROOT}/outputs/metrics",
        ],
        "report_paths": [
            f"{WORKSPACE_ROOT}/reports/literature-review.md",
            f"{WORKSPACE_ROOT}/reports/experiment-report.md",
            f"{WORKSPACE_ROOT}/reports/revision-plan.md",
        ],
        "rules": [
            "Keep manuscript-facing files under /workspace/main.",
            "Keep reusable experiments under /workspace/scripts and generated figures/tables under /workspace/outputs.",
            "Keep readable research notes, audits, and revision plans under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    },
    "proposal": {
        "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
        "workspace_type": "proposal",
        "label": "Research proposal workspace",
        "primary_files": [
            f"{WORKSPACE_ROOT}/main/proposal.md",
            f"{WORKSPACE_ROOT}/main/budget.md",
            f"{WORKSPACE_ROOT}/main/README.md",
        ],
        "script_paths": [
            f"{WORKSPACE_ROOT}/scripts/evidence_scan.py",
            f"{WORKSPACE_ROOT}/scripts/budget_checks.py",
        ],
        "output_paths": [
            f"{WORKSPACE_ROOT}/outputs/evidence",
            f"{WORKSPACE_ROOT}/outputs/tables",
        ],
        "report_paths": [
            f"{WORKSPACE_ROOT}/reports/novelty-assessment.md",
            f"{WORKSPACE_ROOT}/reports/risk-review.md",
            f"{WORKSPACE_ROOT}/reports/revision-plan.md",
        ],
        "rules": [
            "Keep proposal-facing files under /workspace/main.",
            "Keep evidence scans and budget checks under /workspace/scripts.",
            "Keep novelty, risk, and revision reports under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    },
    "software_copyright": {
        "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
        "workspace_type": "software_copyright",
        "label": "Software copyright workspace",
        "primary_files": [
            f"{WORKSPACE_ROOT}/main/software-description.md",
            f"{WORKSPACE_ROOT}/main/source-structure.md",
            f"{WORKSPACE_ROOT}/main/README.md",
        ],
        "script_paths": [
            f"{WORKSPACE_ROOT}/scripts/source_inventory.py",
            f"{WORKSPACE_ROOT}/scripts/compliance_checks.py",
        ],
        "output_paths": [
            f"{WORKSPACE_ROOT}/outputs/source-inventory",
            f"{WORKSPACE_ROOT}/outputs/screenshots",
        ],
        "report_paths": [
            f"{WORKSPACE_ROOT}/reports/material-checklist.md",
            f"{WORKSPACE_ROOT}/reports/compliance-review.md",
            f"{WORKSPACE_ROOT}/reports/revision-plan.md",
        ],
        "rules": [
            "Keep application-facing software documentation under /workspace/main.",
            "Keep source inventory and compliance helper scripts under /workspace/scripts.",
            "Keep material checklists and compliance reviews under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    },
    "patent": {
        "schema": WORKSPACE_TYPE_PROFILE_SCHEMA,
        "workspace_type": "patent",
        "label": "Patent workspace",
        "primary_files": [
            f"{WORKSPACE_ROOT}/main/patent-draft.md",
            f"{WORKSPACE_ROOT}/main/claims.md",
            f"{WORKSPACE_ROOT}/main/drawings-notes.md",
        ],
        "script_paths": [
            f"{WORKSPACE_ROOT}/scripts/prior_art_scan.py",
            f"{WORKSPACE_ROOT}/scripts/claim_checks.py",
        ],
        "output_paths": [
            f"{WORKSPACE_ROOT}/outputs/prior-art",
            f"{WORKSPACE_ROOT}/outputs/claim-maps",
        ],
        "report_paths": [
            f"{WORKSPACE_ROOT}/reports/novelty-map.md",
            f"{WORKSPACE_ROOT}/reports/claim-risk-review.md",
            f"{WORKSPACE_ROOT}/reports/revision-plan.md",
        ],
        "rules": [
            "Keep patent-facing drafts, claims, and drawing notes under /workspace/main.",
            "Keep prior-art and claim-analysis scripts under /workspace/scripts.",
            "Keep novelty maps, claim risk reviews, and revision plans under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    },
}

WORKSPACE_SUPPORTED_TYPES = tuple(_WORKSPACE_TYPE_PROFILES)


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
    outputs_readme_path = root / WORKSPACE_OUTPUTS_README_RELATIVE_PATH
    outputs_readme_path.parent.mkdir(parents=True, exist_ok=True)
    if not outputs_readme_path.exists():
        outputs_readme_path.write_text(WORKSPACE_OUTPUTS_README_TEXT, encoding="utf-8")
    reports_readme_path = root / WORKSPACE_REPORTS_README_RELATIVE_PATH
    reports_readme_path.parent.mkdir(parents=True, exist_ok=True)
    if not reports_readme_path.exists():
        reports_readme_path.write_text(WORKSPACE_REPORTS_README_TEXT, encoding="utf-8")
    dataset_manifest_path = root / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH
    if not dataset_manifest_path.exists():
        dataset_manifest_path.write_text(
            json.dumps(build_dataset_provenance_manifest(), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    artifact_manifest_path = root / WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH
    if not artifact_manifest_path.exists():
        artifact_manifest_path.write_text(
            json.dumps(build_artifact_manifest(), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
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
        "workspace_profile": workspace_type_profile(workspace_type),
        "manifest_path": WORKSPACE_MANIFEST_VIRTUAL_PATH,
        "datasets_manifest_path": WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
        "artifacts_manifest_path": WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH,
        "task_scratch_root": WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT,
        "directories": deepcopy(_DIRECTORY_CONTRACTS),
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "artifact_roots": {
            root["name"]: root["virtual_path"]
            for root in WORKSPACE_ARTIFACT_ROOTS
        },
        "path_classes": deepcopy(WORKSPACE_PATH_CLASSES),
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


def workspace_type_profile(workspace_type: str | None) -> dict[str, Any]:
    """Return domain-specific file naming guidance for the common workspace layout."""

    key = str(workspace_type or "").strip().lower()
    return deepcopy(_WORKSPACE_TYPE_PROFILES.get(key) or _GENERIC_WORKSPACE_PROFILE)


def validate_workspace_type_profile(workspace_type: str) -> dict[str, Any]:
    """Validate that workspace profile guidance stays within the common layout."""

    profile = workspace_type_profile(workspace_type)
    errors: list[str] = []
    expected_roots = {
        "primary_files": f"{WORKSPACE_ROOT}/main/",
        "script_paths": f"{WORKSPACE_ROOT}/scripts/",
        "output_paths": f"{WORKSPACE_ROOT}/outputs",
        "report_paths": f"{WORKSPACE_ROOT}/reports/",
    }
    for field, root in expected_roots.items():
        values = profile.get(field)
        if not isinstance(values, list) or not values:
            errors.append(f"{field} must be a non-empty list")
            continue
        for value in values:
            try:
                normalized = normalize_workspace_virtual_path(str(value))
            except ValueError:
                errors.append(f"{field} contains invalid path: {value}")
                continue
            if is_workspace_protected_path(normalized) or is_workspace_internal_path(normalized):
                errors.append(f"{field} contains protected/internal path: {normalized}")
            if root.endswith("/") and not normalized.startswith(root):
                errors.append(f"{field} path must be under {root}: {normalized}")
            if not root.endswith("/") and normalized != root and not normalized.startswith(f"{root}/"):
                errors.append(f"{field} path must be under {root}: {normalized}")
    return {"workspace_type": workspace_type, "valid": not errors, "errors": errors}


def build_artifact_manifest(*, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return the default editable artifact metadata manifest."""

    return {
        "schema": WORKSPACE_ARTIFACT_MANIFEST_SCHEMA,
        "version": WORKSPACE_ARTIFACT_MANIFEST_VERSION,
        "root": WORKSPACE_ROOT,
        "artifacts": list(artifacts or []),
        "rules": list(WORKSPACE_ARTIFACT_MANIFEST_RULES),
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


def merge_artifact_manifest(
    manifest: Mapping[str, Any] | None,
    artifacts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Merge safe user-reviewable artifact refs into the editable artifact manifest.

    Existing manifest entries are user-authored state and win over incoming
    runtime entries for the same path.
    """

    merged = deepcopy(dict(manifest)) if isinstance(manifest, Mapping) else build_artifact_manifest()
    existing_artifacts = merged.get("artifacts")
    if not isinstance(existing_artifacts, list):
        existing_artifacts = []
    merged["artifacts"] = existing_artifacts

    existing_paths = {
        path
        for item in existing_artifacts
        if isinstance(item, Mapping)
        for path in (_safe_artifact_manifest_path(item.get("path")),)
        if path
    }
    for raw_entry in artifacts or []:
        entry = _safe_artifact_manifest_entry(raw_entry)
        if not entry:
            continue
        path = entry["path"]
        if path in existing_paths:
            continue
        existing_artifacts.append(entry)
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


def _safe_artifact_manifest_entry(raw_entry: Any) -> dict[str, Any] | None:
    if not isinstance(raw_entry, Mapping):
        return None
    path = _safe_artifact_manifest_path(raw_entry.get("path"))
    if not path:
        return None
    entry: dict[str, Any] = {"path": path}
    for key in ARTIFACT_MANIFEST_ALLOWED_FIELDS:
        if key == "path" or key not in raw_entry:
            continue
        if key == "dataset_paths":
            dataset_paths = _safe_artifact_dataset_paths(raw_entry.get(key))
            if dataset_paths:
                entry[key] = dataset_paths
            continue
        if key == "source_script":
            source_script = _safe_script_manifest_path(raw_entry.get(key))
            if source_script:
                entry[key] = source_script
            continue
        value = _safe_artifact_manifest_value(raw_entry.get(key))
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


def _safe_artifact_manifest_path(raw_path: Any) -> str | None:
    try:
        path = normalize_workspace_virtual_path(str(raw_path or ""))
    except ValueError:
        return None
    if not is_user_reviewable_workspace_artifact_path(path):
        return None
    if is_workspace_guidance_path(path) or is_workspace_protected_path(path) or is_workspace_internal_path(path):
        return None
    return path


def _safe_script_manifest_path(raw_path: Any) -> str | None:
    try:
        path = normalize_workspace_virtual_path(str(raw_path or ""))
    except ValueError:
        return None
    if not path.startswith(f"{WORKSPACE_ROOT}/scripts/"):
        return None
    if not path.endswith(".py"):
        return None
    if is_workspace_guidance_path(path) or is_workspace_protected_path(path) or is_workspace_internal_path(path):
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


def _safe_artifact_manifest_value(value: Any) -> Any | None:
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


def _safe_artifact_dataset_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for item in raw_items[:50]:
        path = _safe_dataset_manifest_path(item)
        if path and path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def _contains_workspace_secret_ref(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            f"{WORKSPACE_ROOT}/.wenjin",
            WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT,
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
        "workspace_profile": workspace_type_profile(workspace_type),
        "artifact_roots": manifest["artifact_roots"],
        "path_classes": deepcopy(WORKSPACE_PATH_CLASSES),
        "datasets_manifest_path": WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
        "artifacts_manifest_path": WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH,
        "task_scratch_root": WORKSPACE_TASK_SCRATCH_VIRTUAL_ROOT,
        "runtime_roots": manifest["runtime_roots"],
        "protected_paths": list(WORKSPACE_PROTECTED_PATHS),
        "internal_paths": list(WORKSPACE_INTERNAL_PATHS),
        "search_ignored_names": list(WORKSPACE_SEARCH_IGNORED_NAMES),
        "rules": [
            "Use only /workspace virtual paths when calling sandbox tools.",
            "File search and directory listing skip common generated/cache directories listed in search_ignored_names.",
            "Record reusable dataset provenance in /workspace/datasets/manifest.json.",
            "Write reusable scripts under /workspace/scripts.",
            "Write user-reviewable generated files under /workspace/outputs or /workspace/reports.",
            "Use /workspace/tmp only for scratch data that should not be surfaced by default.",
            "Use /workspace/tmp/tasks for task-scoped scratch files that should not become artifacts.",
            "Do not read or write protected paths.",
            "Do not register or cite internal harness refs as user-facing artifacts.",
        ],
    }


def workspace_virtual_path(relative_path: str) -> str:
    """Resolve a relative workspace path into the canonical virtual namespace."""

    text = str(relative_path or "").strip()
    if "\x00" in text:
        raise ValueError("workspace path contains null byte")
    if not text:
        return WORKSPACE_ROOT
    if text == WORKSPACE_ROOT or text.startswith(f"{WORKSPACE_ROOT}/"):
        return normalize_workspace_virtual_path(text)
    if text.startswith("/"):
        raise ValueError(f"path must be under {WORKSPACE_ROOT}")
    return normalize_workspace_virtual_path(f"{WORKSPACE_ROOT}/{text.strip('/')}")


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


def is_workspace_readable_internal_output_ref(path: str) -> bool:
    """Return whether a direct internal output ref may be read through bounded tools."""

    try:
        normalized = normalize_workspace_virtual_path(path)
    except ValueError:
        return False
    return normalized.startswith(f"{WORKSPACE_HARNESS_OUTPUTS_VIRTUAL_ROOT}/")


def is_workspace_search_ignored_path(path: str) -> bool:
    """Return whether search/listing tools should skip a generated/cache path."""

    try:
        relative = workspace_relative_path(path)
    except ValueError:
        return False
    return any(
        _matches_workspace_pattern(segment, pattern)
        for segment in PurePosixPath(relative).parts
        for pattern in WORKSPACE_SEARCH_IGNORED_NAMES
    )


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

    if is_workspace_guidance_path(path):
        return False
    return workspace_artifact_root_for_path(path) is not None


def is_workspace_guidance_path(path: str) -> bool:
    """Return whether a path is layout guidance or manifest state, not user output."""

    try:
        relative = workspace_relative_path(path)
    except ValueError:
        return False
    return relative in WORKSPACE_GUIDANCE_RELATIVE_PATHS


def classify_workspace_path(path: str) -> WorkspacePathClass:
    """Classify a workspace path for harness policy and UI projection."""

    normalized = normalize_workspace_virtual_path(path)
    if is_workspace_protected_path(normalized):
        return "protected"
    if is_workspace_internal_path(normalized):
        return "internal"
    if is_workspace_guidance_path(normalized):
        return "hidden"
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
