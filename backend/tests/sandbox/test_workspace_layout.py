from __future__ import annotations

import json

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


def test_workspace_sandbox_manifest_does_not_expose_mutable_contract_state():
    first = build_workspace_sandbox_manifest(workspace_id="ws-1")
    first["directories"]["main"]["purpose"] = "mutated"

    second = build_workspace_sandbox_manifest(workspace_id="ws-2")

    assert second["directories"]["main"]["purpose"] == "primary_project"


def test_workspace_protected_paths_include_runtime_and_secret_material():
    assert WORKSPACE_PROTECTED_PATHS == (
        ".git/**",
        ".env",
        "*.pem",
        "*.key",
        ".wenjin/env/**",
        ".wenjin/cache/**",
        ".wenjin/manifest.json",
    )
