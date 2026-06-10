from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.lead_agent.v2.sandbox_artifact_discovery import discover_generated_artifacts
from src.sandbox.providers.local import LocalSandbox
from src.sandbox.workspace_layout import (
    WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH,
    ensure_workspace_sandbox_layout,
)


@pytest.mark.asyncio
async def test_discover_generated_artifacts_skips_artifact_manifest(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")

    generated = await discover_generated_artifacts(sandbox)

    assert [item["path"] for item in generated] == ["/workspace/outputs/result.csv"]
    assert WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH not in {item["path"] for item in generated}


@pytest.mark.asyncio
async def test_discover_generated_artifacts_skips_layout_guidance_files(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/reports/summary.md", "# Summary\n")

    generated = await discover_generated_artifacts(sandbox)

    assert [item["path"] for item in generated] == ["/workspace/reports/summary.md"]
    assert "/workspace/outputs/README.md" not in {item["path"] for item in generated}
    assert "/workspace/reports/README.md" not in {item["path"] for item in generated}


@pytest.mark.asyncio
async def test_discover_generated_artifacts_skips_protected_paths(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
    await sandbox.write_file("/workspace/outputs/.env", "SECRET=must-not-stage\n")
    await sandbox.write_file("/workspace/reports/.env", "TOKEN=must-not-stage\n")

    generated = await discover_generated_artifacts(sandbox)

    assert [item["path"] for item in generated] == ["/workspace/outputs/result.csv"]


@pytest.mark.asyncio
async def test_discover_generated_artifacts_skips_symlinks_to_protected_and_internal_targets(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
    await sandbox.write_file("/workspace/.env", "SECRET=must-not-stage\n")
    await sandbox.write_file(
        "/workspace/tmp/tasks/.harness/outputs/exec/node/tool/stdout.txt",
        "internal output must not stage\n",
    )
    try:
        (Path(tmp_path) / "outputs" / "linked-secret.csv").symlink_to(Path(tmp_path) / ".env")
        (Path(tmp_path) / "outputs" / "linked-internal.txt").symlink_to(
            Path(tmp_path)
            / "tmp"
            / "tasks"
            / ".harness"
            / "outputs"
            / "exec"
            / "node"
            / "tool"
            / "stdout.txt"
        )
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")

    generated = await discover_generated_artifacts(sandbox)

    assert [item["path"] for item in generated] == ["/workspace/outputs/result.csv"]


@pytest.mark.asyncio
async def test_discover_generated_artifacts_enriches_candidates_from_manifest(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
    await sandbox.write_file(
        WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH,
        json.dumps(
            {
                "schema": "wenjin.workspace_sandbox.artifact_manifest.v1",
                "version": 1,
                "root": "/workspace",
                "artifacts": [
                    {
                        "path": "/workspace/outputs/result.csv",
                        "title": "Cleaned panel metrics",
                        "description": "Final table used by the analysis report.",
                        "artifact_kind": "table",
                        "source_script": "/workspace/scripts/analysis.py",
                        "dataset_paths": ["/workspace/datasets/raw.csv"],
                        "notes": "ready for review",
                    },
                    {
                        "path": "/workspace/tmp/tasks/.harness/outputs/exec/stdout.txt",
                        "title": "Internal ref must not enrich",
                    },
                ],
                "rules": [],
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )

    [candidate] = await discover_generated_artifacts(sandbox)

    assert candidate["path"] == "/workspace/outputs/result.csv"
    assert candidate["title"] == "Cleaned panel metrics"
    assert candidate["description"] == "Final table used by the analysis report."
    assert candidate["artifact_kind"] == "table"
    assert candidate["source_script"] == "/workspace/scripts/analysis.py"
    assert candidate["dataset_paths"] == ["/workspace/datasets/raw.csv"]
    assert candidate["notes"] == "ready for review"
