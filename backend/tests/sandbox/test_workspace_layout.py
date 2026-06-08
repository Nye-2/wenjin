from __future__ import annotations

import json

import src.sandbox.workspace_layout as layout
from src.sandbox.workspace_layout import (
    WORKSPACE_MANIFEST_RELATIVE_PATH,
    WORKSPACE_PROTECTED_PATHS,
    WORKSPACE_ROOT,
    WORKSPACE_STANDARD_DIRS,
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
