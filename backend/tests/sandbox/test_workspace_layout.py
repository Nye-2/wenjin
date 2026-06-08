from __future__ import annotations

import json

import src.sandbox.workspace_layout as layout
from src.sandbox.workspace_layout import (
    WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH,
    WORKSPACE_MANIFEST_RELATIVE_PATH,
    WORKSPACE_PROTECTED_PATHS,
    WORKSPACE_ROOT,
    WORKSPACE_STANDARD_DIRS,
    build_dataset_provenance_manifest,
    build_workspace_sandbox_manifest,
    ensure_workspace_sandbox_layout,
)


def test_ensure_workspace_sandbox_layout_creates_standard_tree(tmp_path):
    manifest = ensure_workspace_sandbox_layout(
        tmp_path,
        workspace_id="ws-1",
        sandbox_id="workspace-ws-1",
        workspace_type="sci",
    )

    assert WORKSPACE_ROOT == "/workspace"
    for relative_path in WORKSPACE_STANDARD_DIRS:
        assert (tmp_path / relative_path).is_dir()

    manifest_path = tmp_path / WORKSPACE_MANIFEST_RELATIVE_PATH
    assert manifest_path.is_file()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted == manifest
    assert persisted["schema"] == "wenjin.workspace_sandbox.layout.v1"
    assert persisted["workspace_id"] == "ws-1"
    assert persisted["sandbox_id"] == "workspace-ws-1"
    assert persisted["workspace_type"] == "sci"
    assert persisted["virtual_root"] == "/workspace"
    assert persisted["directories"]["main"]["virtual_path"] == "/workspace/main"
    assert persisted["directories"]["outputs"]["review_surface"] == "artifact"
    assert persisted["datasets_manifest_path"] == "/workspace/datasets/manifest.json"
    assert ".wenjin/env/**" in persisted["protected_paths"]
    assert ".wenjin/cache/**" in persisted["protected_paths"]


def test_workspace_sandbox_layout_manifest_is_stable_when_recreated(tmp_path):
    first = ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")
    second = ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert second == first
    assert json.loads((tmp_path / WORKSPACE_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")) == first


def test_ensure_workspace_sandbox_layout_creates_guidance_and_keep_files(tmp_path):
    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1", workspace_type="sci")

    readme_path = tmp_path / "main" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    assert readme_path.is_file()
    assert "/workspace/datasets" in readme
    assert (tmp_path / "datasets" / "README.md").is_file()
    dataset_manifest = json.loads(
        (tmp_path / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert dataset_manifest == {
        "schema": "wenjin.workspace_sandbox.dataset_provenance.v1",
        "version": 1,
        "root": "/workspace/datasets",
        "datasets": [],
        "rules": [
            "Record every reusable dataset or uploaded input used by sandbox experiments.",
            "Use /workspace/datasets virtual paths only.",
            "Keep secrets, API keys, credentials, and raw private tokens out of this manifest.",
            "Prefer stable source_id, content_hash, license, and preparation notes when known.",
        ],
    }
    assert "/workspace/scripts" in readme
    assert "/workspace/outputs" in readme
    assert "/workspace/reports" in readme
    assert ".wenjin" in readme
    for relative_path in ("datasets/.gitkeep", "scripts/.gitkeep", "outputs/.gitkeep", "reports/.gitkeep"):
        assert (tmp_path / relative_path).is_file()


def test_ensure_workspace_sandbox_layout_preserves_existing_main_readme(tmp_path):
    readme_path = tmp_path / "main" / "README.md"
    readme_path.parent.mkdir(parents=True)
    readme_path.write_text("custom workspace note\n", encoding="utf-8")

    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert readme_path.read_text(encoding="utf-8") == "custom workspace note\n"


def test_ensure_workspace_sandbox_layout_preserves_existing_dataset_manifest(tmp_path):
    manifest_path = tmp_path / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        '{"schema":"custom","datasets":[{"path":"/workspace/datasets/raw.csv"}]}\n',
        encoding="utf-8",
    )

    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert manifest_path.read_text(encoding="utf-8") == (
        '{"schema":"custom","datasets":[{"path":"/workspace/datasets/raw.csv"}]}\n'
    )


def test_merge_dataset_provenance_manifest_adds_safe_refs_without_overwriting_existing():
    existing = build_dataset_provenance_manifest(
        datasets=[
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "title": "User-curated survey",
                "source_id": "user-source",
                "custom_note": "kept",
            }
        ]
    )

    merged = layout.merge_dataset_provenance_manifest(
        existing,
        [
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "title": "Runtime title should not overwrite",
                "source_id": "runtime-source",
            },
            {
                "path": "/workspace/datasets/clean/panel.csv",
                "source_id": "source-2",
                "name": "panel.csv",
                "title": "Clean panel",
                "description": "Prepared source data",
                "format": "csv",
                "mime_type": "text/csv",
                "size_bytes": 2048,
                "content_hash": "sha256:abc",
                "license": "CC-BY-4.0",
                "preparation": "normalized columns",
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T01:00:00Z",
                "private_token": "must not persist",
            },
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "title": "User-curated survey",
            "source_id": "user-source",
            "custom_note": "kept",
        },
        {
            "path": "/workspace/datasets/clean/panel.csv",
            "source_id": "source-2",
            "name": "panel.csv",
            "title": "Clean panel",
            "description": "Prepared source data",
            "format": "csv",
            "mime_type": "text/csv",
            "size_bytes": 2048,
            "content_hash": "sha256:abc",
            "license": "CC-BY-4.0",
            "preparation": "normalized columns",
            "created_at": "2026-06-08T00:00:00Z",
            "updated_at": "2026-06-08T01:00:00Z",
        },
    ]


def test_merge_dataset_provenance_manifest_rejects_non_dataset_and_guidance_refs():
    merged = layout.merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        [
            {"path": "/workspace/datasets"},
            {"path": "/workspace/datasets/manifest.json"},
            {"path": "/workspace/datasets/README.md"},
            {"path": "/workspace/datasets/.gitkeep"},
            {"path": "/workspace/outputs/result.csv"},
            {"path": "/workspace/outputs/harness/exec/tool.txt"},
            {"path": "/workspace/main/.env"},
            {"path": "/mnt/user-data/datasets/raw.csv"},
            {"path": "/workspace/datasets/raw/valid.csv", "source_id": "source-1"},
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/valid.csv",
            "source_id": "source-1",
        }
    ]


def test_merge_dataset_provenance_manifest_drops_host_path_values():
    merged = layout.merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        [
            {
                "path": "/workspace/datasets/raw/valid.csv",
                "source_id": "source-1",
                "description": "copied from /Users/ze/private/raw.csv",
                "preparation": "safe preparation note",
            },
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/valid.csv",
            "source_id": "source-1",
            "preparation": "safe preparation note",
        }
    ]


def test_workspace_sandbox_manifest_does_not_expose_mutable_contract_state():
    first = build_workspace_sandbox_manifest(workspace_id="ws-1")
    first["directories"]["main"]["purpose"] = "mutated"

    second = build_workspace_sandbox_manifest(workspace_id="ws-2")

    assert second["directories"]["main"]["purpose"] == "primary_project"


def test_workspace_protected_paths_include_runtime_and_secret_material():
    assert WORKSPACE_PROTECTED_PATHS == (
        ".git/**",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "*.pem",
        "*.key",
        ".wenjin/env/**",
        ".wenjin/cache/**",
        ".wenjin/manifest.json",
    )


def test_workspace_virtual_path_normalization_rejects_outside_and_traversal_paths():
    assert (
        layout.normalize_workspace_virtual_path("/workspace/main/paper.tex")
        == "/workspace/main/paper.tex"
    )
    assert (
        layout.normalize_workspace_virtual_path("/tmp/ws/workspace/reports/summary.md")
        == "/workspace/reports/summary.md"
    )
    assert layout.workspace_relative_path("/workspace/reports/summary.md") == "reports/summary.md"

    for invalid in (
        "/mnt/user-data/outputs/report.md",
        "/workspace/outputs/../secrets.txt",
        "/workspace/main\x00.tex",
    ):
        try:
            layout.normalize_workspace_virtual_path(invalid)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError(f"expected invalid workspace path: {invalid}")


def test_workspace_path_classification_is_centralized_for_harness_boundaries():
    assert layout.is_workspace_protected_path("/workspace/.wenjin/env/python/bin/python")
    assert layout.is_workspace_protected_path("/workspace/.env")
    assert layout.is_workspace_protected_path("/workspace/.env.local")
    assert layout.is_workspace_protected_path("/workspace/main/.env")
    assert layout.is_workspace_protected_path("/workspace/scripts/.env.local")
    assert layout.is_workspace_internal_path(
        "/workspace/outputs/harness/exec-1/node/tool.txt"
    )
    assert not layout.is_user_reviewable_workspace_artifact_path(
        "/workspace/outputs/harness/exec-1/node/tool.txt"
    )
    assert layout.is_user_reviewable_workspace_artifact_path("/workspace/outputs/figure.png")
    assert layout.is_user_reviewable_workspace_artifact_path("/workspace/reports/summary.md")
    assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/main/analysis.py")
    assert layout.workspace_artifact_root_for_path("/workspace/reports/summary.md") == {
        "name": "reports",
        "virtual_path": "/workspace/reports",
        "artifact_kind": "sandbox_report",
    }

    assert (
        layout.classify_workspace_path("/workspace/.wenjin/cache/pip/index")
        == "protected"
    )
    assert layout.classify_workspace_path("/workspace/main/.env") == "protected"
    assert layout.classify_workspace_path("/workspace/scripts/.env.local") == "protected"
    assert (
        layout.classify_workspace_path("/workspace/outputs/harness/exec/tool.txt")
        == "internal"
    )
    assert layout.classify_workspace_path("/workspace/reports/summary.md") == "artifact"
    assert layout.classify_workspace_path("/workspace/tmp/scratch.json") == "hidden"
    assert layout.classify_workspace_path("/workspace/main/paper.tex") == "workspace"
