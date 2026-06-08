from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext
from src.agents.harness.sandbox_tools import (
    HarnessPathError,
    SandboxFileTools,
)
from src.sandbox.providers.local import LocalSandbox
from src.sandbox.workspace_layout import (
    WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH,
    WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
    WORKSPACE_PROTECTED_PATHS,
)


@pytest.fixture
def sandbox():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        yield LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})


def _ctx() -> HarnessRunContext:
    return HarnessRunContext(
        workspace_id="ws-1",
        user_id="user-1",
        execution_id="exec-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
    )


def _write_policy(**overrides) -> HarnessPolicy:
    return HarnessPolicy(
        permissions=frozenset({"filesystem.read", "filesystem.write", "filesystem.diff"}),
        **overrides,
    )


def _write_without_diff_policy(**overrides) -> HarnessPolicy:
    return HarnessPolicy(
        permissions=frozenset({"filesystem.write"}),
        **overrides,
    )


def _read_policy(**overrides) -> HarnessPolicy:
    return HarnessPolicy(
        permissions=frozenset({"filesystem.read"}),
        **overrides,
    )


@pytest.mark.asyncio
async def test_read_file_returns_bounded_preview(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "line 1\nline 2\nline 3\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    result = await tools.read_file(path="/workspace/main.tex", start_line=2, end_line=2)

    assert result.structured_payload["path"] == "/workspace/main.tex"
    assert result.preview_text == "line 2\n"
    assert not result.truncated


@pytest.mark.asyncio
async def test_file_tools_reject_host_absolute_paths_that_contain_workspace_segment(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/visible.txt", "alpha\n")
    host_path = str(Path(sandbox.path_mappings["/workspace"]) / "main" / "visible.txt")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="path must be under /workspace"):
        await tools.read_file(path=host_path)

    with pytest.raises(HarnessPathError, match="path must be under /workspace"):
        await tools.list_dir(path=str(Path(sandbox.path_mappings["/workspace"]) / "main"))

    with pytest.raises(HarnessPathError, match="path must be under /workspace"):
        await tools.write_file(path=host_path, content="bad\n")

    assert await sandbox.read_file("/workspace/main/visible.txt") == "alpha\n"


@pytest.mark.asyncio
async def test_read_tools_require_filesystem_read_permission(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=HarnessPolicy())

    with pytest.raises(PermissionError, match="filesystem reads"):
        await tools.read_file(path="/workspace/main.tex")

    with pytest.raises(PermissionError, match="filesystem reads"):
        await tools.list_dir(path="/workspace")

    with pytest.raises(PermissionError, match="filesystem reads"):
        await tools.glob(pattern="**/*.tex")

    with pytest.raises(PermissionError, match="filesystem reads"):
        await tools.grep(pattern="alpha", glob="**/*.tex")


@pytest.mark.asyncio
async def test_read_file_externalizes_large_selected_output(sandbox: LocalSandbox) -> None:
    content = "".join(f"line {index:03d}: {'x' * 20}\n" for index in range(1, 31))
    await sandbox.write_file("/workspace/main/large.txt", content)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(
            output_budget={
                "read_max_chars": 120,
                "externalize_above_chars": 200,
                "preview_head_chars": 60,
                "preview_tail_chars": 40,
            }
        ),
    )

    result = await tools.read_file(path="/workspace/main/large.txt")

    assert result.truncated
    assert result.externalized
    assert len(result.output_refs) == 1
    assert result.output_refs[0].startswith(
        "/workspace/outputs/harness/exec-1/node-1/invocation-1/sandbox.read_file-"
    )
    assert result.output_refs[0].endswith(".txt")
    assert "Full sandbox.read_file output saved to" in result.preview_text
    assert "line 001" in result.preview_text
    assert "line 030" in result.preview_text
    assert await sandbox.read_file(result.output_refs[0]) == content


@pytest.mark.asyncio
async def test_read_file_externalized_refs_do_not_overwrite_same_invocation(sandbox: LocalSandbox) -> None:
    first = "first\n" * 80
    second = "second\n" * 80
    await sandbox.write_file("/workspace/main/first.txt", first)
    await sandbox.write_file("/workspace/main/second.txt", second)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"externalize_above_chars": 100}),
    )

    first_result = await tools.read_file(path="/workspace/main/first.txt")
    second_result = await tools.read_file(path="/workspace/main/second.txt")

    assert first_result.output_refs != second_result.output_refs
    assert await sandbox.read_file(first_result.output_refs[0]) == first
    assert await sandbox.read_file(second_result.output_refs[0]) == second


@pytest.mark.asyncio
async def test_read_file_request_cannot_exceed_policy_max_chars(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/large.txt", "x" * 80)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(
            output_budget={
                "read_max_chars": 20,
                "externalize_above_chars": 200,
            }
        ),
    )

    oversized = await tools.read_file(path="/workspace/main/large.txt", max_chars=60)
    narrower = await tools.read_file(path="/workspace/main/large.txt", max_chars=8)

    assert oversized.truncated
    assert len(oversized.preview_text) == 20
    assert narrower.truncated
    assert len(narrower.preview_text) == 8


@pytest.mark.asyncio
async def test_externalized_read_file_preview_cannot_exceed_policy_content_budget(sandbox: LocalSandbox) -> None:
    content = "~" * 100
    await sandbox.write_file("/workspace/main/large.txt", content)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(
            output_budget={
                "read_max_chars": 20,
                "externalize_above_chars": 30,
                "preview_head_chars": 60,
                "preview_tail_chars": 40,
            }
        ),
    )

    result = await tools.read_file(path="/workspace/main/large.txt")

    assert result.externalized
    assert result.preview_text.count("~") == 20
    assert await sandbox.read_file(result.output_refs[0]) == content


@pytest.mark.asyncio
async def test_write_file_records_diff_and_hashes(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "old\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.write_file(path="/workspace/main.tex", content="new\n")

    assert await sandbox.read_file("/workspace/main.tex") == "new\n"
    assert result.file_change is not None
    assert result.file_change["operation"] == "update"
    assert "-old" in result.file_change["unified_diff"]
    assert "+new" in result.file_change["unified_diff"]
    assert result.file_change["before_hash"] != result.file_change["after_hash"]


@pytest.mark.asyncio
async def test_apply_patch_applies_multi_file_edits_and_records_file_changes(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/paper.tex", "Title: Old\nBody\n")
    await sandbox.write_file("/workspace/scripts/analysis.py", "print('old')\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.apply_patch(
        edits=[
            {
                "path": "/workspace/main/paper.tex",
                "operation": "replace",
                "old": "Title: Old",
                "new": "Title: New",
            },
            {
                "path": "/workspace/scripts/analysis.py",
                "old": "print('old')",
                "new": "print('new')",
            },
            {
                "path": "/workspace/reports/summary.md",
                "operation": "write",
                "new": "# Summary\n\nUpdated.",
            },
        ]
    )

    assert await sandbox.read_file("/workspace/main/paper.tex") == "Title: New\nBody\n"
    assert await sandbox.read_file("/workspace/scripts/analysis.py") == "print('new')\n"
    assert await sandbox.read_file("/workspace/reports/summary.md") == "# Summary\n\nUpdated."
    assert result.structured_payload == {
        "schema": "wenjin.harness.structured_patch.v1",
        "edit_count": 3,
        "changed_paths": [
            "/workspace/main/paper.tex",
            "/workspace/scripts/analysis.py",
            "/workspace/reports/summary.md",
        ],
    }
    assert [change["path"] for change in result.file_changes] == [
        "/workspace/main/paper.tex",
        "/workspace/scripts/analysis.py",
        "/workspace/reports/summary.md",
    ]
    assert "-Title: Old" in result.file_changes[0]["unified_diff"]
    assert "+Title: New" in result.file_changes[0]["unified_diff"]
    assert result.file_changes[2]["operation"] == "add"


@pytest.mark.asyncio
async def test_apply_patch_validates_all_edits_before_mutating(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/paper.tex", "alpha\n")
    await sandbox.write_file("/workspace/scripts/analysis.py", "beta\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(ValueError, match="expected exactly one match"):
        await tools.apply_patch(
            edits=[
                {
                    "path": "/workspace/main/paper.tex",
                    "old": "alpha",
                    "new": "changed",
                },
                {
                    "path": "/workspace/scripts/analysis.py",
                    "old": "missing",
                    "new": "changed",
                },
            ]
        )

    assert await sandbox.read_file("/workspace/main/paper.tex") == "alpha\n"
    assert await sandbox.read_file("/workspace/scripts/analysis.py") == "beta\n"


@pytest.mark.asyncio
async def test_apply_patch_requires_explicit_new_text(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/paper.tex", "alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(ValueError, match="new text is required"):
        await tools.apply_patch(
            edits=[
                {
                    "path": "/workspace/main/paper.tex",
                    "old": "alpha",
                }
            ]
        )

    assert await sandbox.read_file("/workspace/main/paper.tex") == "alpha\n"


@pytest.mark.asyncio
async def test_register_dataset_updates_manifest_and_records_diff(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/datasets/sample.csv", "x,y\n1,2\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.register_dataset(
        path="/workspace/datasets/sample.csv",
        source_id="upload-1",
        name="Sample data",
        content_hash="sha256:abc123",
        license="CC-BY-4.0",
        preparation="Filtered invalid rows.",
    )

    manifest = json.loads(await sandbox.read_file(WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH))
    assert manifest["schema"] == "wenjin.workspace_sandbox.dataset_provenance.v1"
    assert manifest["datasets"] == [
        {
            "path": "/workspace/datasets/sample.csv",
            "source_id": "upload-1",
            "name": "Sample data",
            "content_hash": "sha256:abc123",
            "license": "CC-BY-4.0",
            "preparation": "Filtered invalid rows.",
        }
    ]
    assert result.structured_payload["schema"] == "wenjin.harness.dataset_registration.v1"
    assert result.structured_payload["status"] == "registered"
    assert result.structured_payload["manifest_path"] == WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH
    assert result.file_change is not None
    assert result.file_change["path"] == WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH
    assert "+      \"path\": \"/workspace/datasets/sample.csv\"" in result.file_change["unified_diff"]


@pytest.mark.asyncio
async def test_register_dataset_preserves_existing_user_authored_entry(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/datasets/sample.csv", "x,y\n1,2\n")
    await sandbox.write_file(
        WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
        json.dumps(
            {
                "schema": "wenjin.workspace_sandbox.dataset_provenance.v1",
                "version": 1,
                "root": "/workspace/datasets",
                "datasets": [
                    {
                        "path": "/workspace/datasets/sample.csv",
                        "source_id": "user-kept",
                        "license": "custom",
                    }
                ],
                "rules": [],
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.register_dataset(
        path="/workspace/datasets/sample.csv",
        source_id="agent-attempt",
        license="MIT",
    )

    manifest = json.loads(await sandbox.read_file(WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH))
    assert manifest["datasets"] == [
        {
            "path": "/workspace/datasets/sample.csv",
            "source_id": "user-kept",
            "license": "custom",
        }
    ]
    assert result.structured_payload["status"] == "already_registered"
    assert result.file_change is None


@pytest.mark.asyncio
async def test_register_dataset_rejects_non_dataset_paths_and_drops_host_refs(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/datasets/sample.csv", "x,y\n1,2\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="dataset path must be under /workspace/datasets"):
        await tools.register_dataset(path="/workspace/outputs/result.csv", source_id="bad")

    await tools.register_dataset(
        path="/workspace/datasets/sample.csv",
        source_id="upload-1",
        preparation="generated from /Users/ze/private/raw.csv with token sk-secret",
    )

    manifest_text = await sandbox.read_file(WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH)
    assert "/Users/ze/private" not in manifest_text
    assert "sk-secret" not in manifest_text
    assert json.loads(manifest_text)["datasets"] == [
        {
            "path": "/workspace/datasets/sample.csv",
            "source_id": "upload-1",
        }
    ]


@pytest.mark.asyncio
async def test_register_artifact_updates_manifest_and_records_diff(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.register_artifact(
        path="/workspace/outputs/result.csv",
        title="Cleaned panel metrics",
        description="Final table used by the analysis report.",
        artifact_kind="table",
        source_script="/workspace/scripts/analysis.py",
        dataset_paths=["/workspace/datasets/sample.csv", "/workspace/.env"],
        notes="ready for review",
    )

    manifest = json.loads(await sandbox.read_file(WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH))
    assert manifest["schema"] == "wenjin.workspace_sandbox.artifact_manifest.v1"
    assert manifest["artifacts"] == [
        {
            "path": "/workspace/outputs/result.csv",
            "title": "Cleaned panel metrics",
            "description": "Final table used by the analysis report.",
            "artifact_kind": "table",
            "source_script": "/workspace/scripts/analysis.py",
            "dataset_paths": ["/workspace/datasets/sample.csv"],
            "notes": "ready for review",
        }
    ]
    assert result.structured_payload["schema"] == "wenjin.harness.artifact_registration.v1"
    assert result.structured_payload["status"] == "registered"
    assert result.structured_payload["manifest_path"] == WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH
    assert result.file_change is not None
    assert result.file_change["path"] == WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH


@pytest.mark.asyncio
async def test_register_artifact_preserves_existing_user_authored_entry(sandbox: LocalSandbox) -> None:
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
                        "title": "User title",
                        "artifact_kind": "table",
                    }
                ],
                "rules": [],
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.register_artifact(
        path="/workspace/outputs/result.csv",
        title="Agent title",
        artifact_kind="figure",
    )

    manifest = json.loads(await sandbox.read_file(WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH))
    assert manifest["artifacts"] == [
        {
            "path": "/workspace/outputs/result.csv",
            "title": "User title",
            "artifact_kind": "table",
        }
    ]
    assert result.structured_payload["status"] == "already_registered"
    assert result.file_change is None


@pytest.mark.asyncio
async def test_register_artifact_rejects_internal_and_non_artifact_paths(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="artifact path must be under /workspace/outputs or /workspace/reports"):
        await tools.register_artifact(path="/workspace/main/paper.tex", title="bad")

    with pytest.raises(HarnessPathError, match="artifact path must be under /workspace/outputs or /workspace/reports"):
        await tools.register_artifact(path="/workspace/outputs/harness/exec/stdout.txt", title="bad")

    await tools.register_artifact(
        path="/workspace/outputs/result.csv",
        title="Result",
        notes="copied from /Users/ze/private/raw.csv with token sk-secret",
    )

    manifest_text = await sandbox.read_file(WORKSPACE_ARTIFACTS_MANIFEST_VIRTUAL_PATH)
    assert "/Users/ze/private" not in manifest_text
    assert "sk-secret" not in manifest_text
    assert json.loads(manifest_text)["artifacts"] == [
        {
            "path": "/workspace/outputs/result.csv",
            "title": "Result",
        }
    ]


@pytest.mark.asyncio
async def test_write_tools_require_diff_permission_before_mutating(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "old\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_write_without_diff_policy(),
    )

    with pytest.raises(PermissionError, match="filesystem diff"):
        await tools.write_file(path="/workspace/main.tex", content="new\n")
    assert await sandbox.read_file("/workspace/main.tex") == "old\n"

    with pytest.raises(PermissionError, match="filesystem diff"):
        await tools.str_replace(path="/workspace/main.tex", old="old", new="new")
    assert await sandbox.read_file("/workspace/main.tex") == "old\n"

    with pytest.raises(PermissionError, match="filesystem diff"):
        await tools.apply_patch(edits=[{"path": "/workspace/main.tex", "old": "old", "new": "new"}])
    assert await sandbox.read_file("/workspace/main.tex") == "old\n"


@pytest.mark.asyncio
async def test_write_file_externalizes_large_diff(sandbox: LocalSandbox) -> None:
    before = "".join(f"old line {index:03d}: {'x' * 20}\n" for index in range(1, 41))
    after = "".join(f"new line {index:03d}: {'y' * 20}\n" for index in range(1, 41))
    await sandbox.write_file("/workspace/main/large.tex", before)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_write_policy(
            output_budget={
                "diff_externalize_above_chars": 200,
                "diff_preview_head_chars": 90,
                "diff_preview_tail_chars": 70,
            }
        ),
    )

    result = await tools.write_file(path="/workspace/main/large.tex", content=after)

    assert result.file_change is not None
    change = result.file_change
    assert change["diff_externalized"] is True
    assert change["diff_truncated"] is True
    assert len(change["diff_output_refs"]) == 1
    diff_ref = change["diff_output_refs"][0]
    assert diff_ref.startswith(
        "/workspace/outputs/harness/exec-1/node-1/invocation-1/sandbox.write_file.diff-"
    )
    assert diff_ref.endswith(".diff")
    assert "Full sandbox.write_file.diff output saved to" in change["unified_diff"]
    full_diff = await sandbox.read_file(diff_ref)
    assert "-old line 001" in full_diff
    assert "+new line 040" in full_diff
    assert full_diff != change["unified_diff"]


@pytest.mark.asyncio
async def test_str_replace_requires_unique_match(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "same\nsame\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(ValueError, match="expected exactly one match"):
        await tools.str_replace(path="/workspace/main.tex", old="same", new="changed")


@pytest.mark.asyncio
async def test_grep_and_glob_stay_inside_workspace(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/a.txt", "alpha\n")
    await sandbox.write_file("/workspace/nested/b.txt", "beta alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    glob_result = await tools.glob(pattern="**/*.txt")
    grep_result = await tools.grep(pattern="alpha", glob="**/*.txt")

    assert glob_result.structured_payload["matches"] == [
        "/workspace/a.txt",
        "/workspace/nested/b.txt",
    ]
    assert [item["path"] for item in grep_result.structured_payload["matches"]] == [
        "/workspace/a.txt",
        "/workspace/nested/b.txt",
    ]


@pytest.mark.asyncio
async def test_listing_and_search_hide_protected_and_internal_paths(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/visible.txt", "alpha visible\n")
    await sandbox.write_file("/workspace/outputs/result.txt", "alpha artifact\n")
    await sandbox.write_file("/workspace/.env", "alpha secret\n")
    await sandbox.write_file("/workspace/.wenjin/env/python/bin/python", "alpha runtime\n")
    await sandbox.write_file("/workspace/outputs/harness/exec/node/tool.txt", "alpha internal\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(protected_paths=WORKSPACE_PROTECTED_PATHS),
    )

    list_result = await tools.list_dir(path="/workspace", max_depth=3)
    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    glob_result = await tools.glob(pattern="**/*.txt")
    grep_result = await tools.grep(pattern="alpha", glob="**/*")
    searched_paths = [item["path"] for item in grep_result.structured_payload["matches"]]

    assert "/workspace/main/visible.txt" in listed_paths
    assert "/workspace/outputs/result.txt" in listed_paths
    assert "/workspace/main/visible.txt" in glob_result.structured_payload["matches"]
    assert "/workspace/outputs/result.txt" in searched_paths
    assert all(not path.startswith("/workspace/.env") for path in listed_paths)
    assert all(not path.startswith("/workspace/.wenjin") for path in listed_paths)
    assert all(not path.startswith("/workspace/outputs/harness") for path in listed_paths)
    assert all(not path.startswith("/workspace/.env") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/.wenjin") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/outputs/harness") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/.env") for path in searched_paths)
    assert all(not path.startswith("/workspace/.wenjin") for path in searched_paths)
    assert all(not path.startswith("/workspace/outputs/harness") for path in searched_paths)


@pytest.mark.asyncio
async def test_direct_file_tools_block_internal_harness_output_paths(sandbox: LocalSandbox) -> None:
    internal_path = "/workspace/outputs/harness/exec-1/node-1/invocation-1/full-output.txt"
    await sandbox.write_file(internal_path, "internal full output\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="internal path"):
        await tools.read_file(path=internal_path)

    with pytest.raises(HarnessPathError, match="internal path"):
        await tools.write_file(path=internal_path, content="changed\n")

    with pytest.raises(HarnessPathError, match="internal path"):
        await tools.str_replace(path=internal_path, old="internal", new="changed")

    assert await sandbox.read_file(internal_path) == "internal full output\n"


@pytest.mark.asyncio
async def test_default_policy_hides_workspace_runtime_paths(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/visible.txt", "alpha visible\n")
    await sandbox.write_file("/workspace/.env", "alpha secret\n")
    await sandbox.write_file("/workspace/main/.env", "alpha nested secret\n")
    await sandbox.write_file("/workspace/scripts/.env.local", "alpha local secret\n")
    await sandbox.write_file("/workspace/.wenjin/state/debug.json", "alpha state\n")
    await sandbox.write_file("/workspace/.wenjin/env/python/bin/python", "alpha runtime\n")
    await sandbox.write_file("/workspace/.wenjin/cache/package.txt", "alpha cache\n")
    await sandbox.write_file("/workspace/.wenjin/manifest.json", "alpha manifest\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"filesystem.read"})),
    )

    list_result = await tools.list_dir(path="/workspace", max_depth=3)
    glob_result = await tools.glob(pattern="**/*")
    grep_result = await tools.grep(pattern="alpha", glob="**/*")

    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    glob_paths = glob_result.structured_payload["matches"]
    grep_paths = [item["path"] for item in grep_result.structured_payload["matches"]]
    assert "/workspace/main/visible.txt" in listed_paths
    assert "/workspace/main/visible.txt" in glob_paths
    assert "/workspace/main/visible.txt" in grep_paths
    for paths in (listed_paths, glob_paths, grep_paths):
        assert all(not path.startswith("/workspace/.env") for path in paths)
        assert all(not path.startswith("/workspace/.wenjin") for path in paths)
        assert all(path != "/workspace/main/.env" for path in paths)
        assert all(path != "/workspace/scripts/.env.local" for path in paths)
    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.read_file(path="/workspace/main/.env")
    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.read_file(path="/workspace/.wenjin/state/debug.json")
    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.write_file(path="/workspace/.wenjin/state/debug.json", content="bad\n")
    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.str_replace(path="/workspace/.wenjin/state/debug.json", old="alpha", new="bad")


@pytest.mark.asyncio
async def test_listing_and_search_hide_symlink_escapes(sandbox: LocalSandbox) -> None:
    workspace_root = Path(sandbox.path_mappings["/workspace"])
    outside_dir = workspace_root.parent / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("outside secret alpha\n", encoding="utf-8")
    link_path = workspace_root / "main" / "outside-secret.txt"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(outside_file)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")
    await sandbox.write_file("/workspace/main/visible.txt", "visible alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    list_result = await tools.list_dir(path="/workspace", max_depth=2)
    glob_result = await tools.glob(pattern="main/*.txt")
    grep_result = await tools.grep(pattern="alpha", glob="main/*.txt")

    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    assert "/workspace/main/visible.txt" in listed_paths
    assert "/workspace/main/outside-secret.txt" not in listed_paths
    assert str(outside_file) not in listed_paths
    assert glob_result.structured_payload["matches"] == ["/workspace/main/visible.txt"]
    assert [item["path"] for item in grep_result.structured_payload["matches"]] == [
        "/workspace/main/visible.txt",
    ]


@pytest.mark.asyncio
async def test_direct_file_tools_block_symlink_escapes_at_harness_boundary(sandbox: LocalSandbox) -> None:
    workspace_root = Path(sandbox.path_mappings["/workspace"])
    outside_dir = workspace_root.parent / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("outside secret\n", encoding="utf-8")
    link_path = workspace_root / "main" / "outside-secret.txt"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(outside_file)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="outside workspace"):
        await tools.read_file(path="/workspace/main/outside-secret.txt")

    with pytest.raises(HarnessPathError, match="outside workspace"):
        await tools.write_file(path="/workspace/main/outside-secret.txt", content="changed\n")

    with pytest.raises(HarnessPathError, match="outside workspace"):
        await tools.str_replace(path="/workspace/main/outside-secret.txt", old="outside", new="changed")

    assert outside_file.read_text(encoding="utf-8") == "outside secret\n"


@pytest.mark.asyncio
async def test_direct_file_tools_block_symlinks_to_protected_workspace_targets(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/.env", "SECRET=1\n")
    workspace_root = Path(sandbox.path_mappings["/workspace"])
    link_path = workspace_root / "main" / "linked-secret.txt"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(workspace_root / ".env")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="protected target"):
        await tools.read_file(path="/workspace/main/linked-secret.txt")

    with pytest.raises(HarnessPathError, match="protected target"):
        await tools.write_file(path="/workspace/main/linked-secret.txt", content="changed\n")

    with pytest.raises(HarnessPathError, match="protected target"):
        await tools.str_replace(path="/workspace/main/linked-secret.txt", old="SECRET", new="CHANGED")

    assert await sandbox.read_file("/workspace/.env") == "SECRET=1\n"


@pytest.mark.asyncio
async def test_listing_and_search_hide_symlinks_to_protected_workspace_targets(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/.env", "alpha secret\n")
    await sandbox.write_file("/workspace/main/visible.txt", "alpha visible\n")
    workspace_root = Path(sandbox.path_mappings["/workspace"])
    link_path = workspace_root / "main" / "linked-secret.txt"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(workspace_root / ".env")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    list_result = await tools.list_dir(path="/workspace/main", max_depth=1)
    glob_result = await tools.glob(pattern="main/*.txt")
    grep_result = await tools.grep(pattern="alpha", glob="main/*.txt")

    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    assert "/workspace/main/visible.txt" in listed_paths
    assert "/workspace/main/linked-secret.txt" not in listed_paths
    assert glob_result.structured_payload["matches"] == ["/workspace/main/visible.txt"]
    assert [item["path"] for item in grep_result.structured_payload["matches"]] == [
        "/workspace/main/visible.txt",
    ]


@pytest.mark.asyncio
async def test_file_tools_hide_symlinks_to_internal_workspace_targets(sandbox: LocalSandbox) -> None:
    internal_path = "/workspace/outputs/harness/exec-1/node-1/invocation-1/full-output.txt"
    await sandbox.write_file(internal_path, "alpha internal\n")
    await sandbox.write_file("/workspace/main/visible.txt", "alpha visible\n")
    workspace_root = Path(sandbox.path_mappings["/workspace"])
    link_path = workspace_root / "main" / "linked-internal.txt"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    internal_target = workspace_root / "outputs" / "harness" / "exec-1" / "node-1" / "invocation-1" / "full-output.txt"
    try:
        link_path.symlink_to(internal_target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(HarnessPathError, match="internal target"):
        await tools.read_file(path="/workspace/main/linked-internal.txt")

    list_result = await tools.list_dir(path="/workspace/main", max_depth=1)
    glob_result = await tools.glob(pattern="main/*.txt")
    grep_result = await tools.grep(pattern="alpha", glob="main/*.txt")

    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    assert "/workspace/main/visible.txt" in listed_paths
    assert "/workspace/main/linked-internal.txt" not in listed_paths
    assert glob_result.structured_payload["matches"] == ["/workspace/main/visible.txt"]
    assert [item["path"] for item in grep_result.structured_payload["matches"]] == [
        "/workspace/main/visible.txt",
    ]


@pytest.mark.asyncio
async def test_list_dir_accepts_current_virtual_workspace_root(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.py", "print('ok')\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    result = await tools.list_dir(path="/workspace", max_depth=1)

    assert "/workspace/main.py" in result.preview_text
    assert result.structured_payload["entries"][0]["path"] == "/workspace/main.py"


@pytest.mark.asyncio
async def test_list_dir_caps_structured_entries(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"item {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"search_max_matches": 5}),
    )

    result = await tools.list_dir(path="/workspace/main", max_depth=1)

    assert result.truncated
    assert result.structured_payload["total_entries"] == 8
    assert result.structured_payload["returned_entries"] == 5
    assert len(result.structured_payload["entries"]) == 5
    assert len(result.preview_text.splitlines()) == 5


@pytest.mark.asyncio
async def test_glob_reports_returned_matches_and_limit(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"item {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"search_max_matches": 5}),
    )

    result = await tools.glob(pattern="main/*.txt")

    assert result.truncated
    assert result.structured_payload["match_limit"] == 5
    assert result.structured_payload["returned_matches"] == 5
    assert len(result.structured_payload["matches"]) == 5
    assert len(result.preview_text.splitlines()) == 5


@pytest.mark.asyncio
async def test_search_tools_skip_common_generated_and_cache_directories(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/app.py", "alpha app\n")
    await sandbox.write_file("/workspace/node_modules/pkg/skip.py", "alpha dependency\n")
    await sandbox.write_file("/workspace/main/__pycache__/skip.py", "alpha bytecode\n")
    await sandbox.write_file("/workspace/.pytest_cache/skip.txt", "alpha cache\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    list_result = await tools.list_dir(path="/workspace", max_depth=3)
    glob_result = await tools.glob(pattern="**/*.py")
    grep_result = await tools.grep(pattern="alpha", glob="**/*")
    listed_paths = [item["path"] for item in list_result.structured_payload["entries"]]
    grep_paths = [item["path"] for item in grep_result.structured_payload["matches"]]

    assert "/workspace/main/app.py" in listed_paths
    assert all("node_modules" not in path for path in listed_paths)
    assert all("__pycache__" not in path for path in listed_paths)
    assert all(".pytest_cache" not in path for path in listed_paths)
    assert glob_result.structured_payload["matches"] == ["/workspace/main/app.py"]
    assert grep_paths == ["/workspace/main/app.py"]


@pytest.mark.asyncio
async def test_grep_reports_returned_matches_and_limit(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"alpha {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"search_max_matches": 5}),
    )

    result = await tools.grep(pattern="alpha", glob="main/*.txt")

    assert result.truncated
    assert result.structured_payload["match_limit"] == 5
    assert result.structured_payload["returned_matches"] == 5
    assert len(result.structured_payload["matches"]) == 5
    assert len(result.preview_text.splitlines()) == 5


@pytest.mark.asyncio
async def test_grep_literal_mode_treats_pattern_as_plain_text(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/math.txt", "price = (a+b)\nregex would match ab\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    result = await tools.grep(pattern="(a+b)", glob="main/*.txt", literal=True)

    assert result.structured_payload["literal"] is True
    assert result.structured_payload["matches"] == [
        {"path": "/workspace/main/math.txt", "line": 1, "text": "price = (a+b)"}
    ]


@pytest.mark.asyncio
async def test_grep_invalid_regex_returns_recoverable_tool_error(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/file.txt", "alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    result = await tools.grep(pattern="[", glob="main/*.txt")

    assert result.error is not None
    assert "invalid regular expression" in result.preview_text
    assert result.structured_payload["error_code"] == "invalid_regex"
    assert result.structured_payload["pattern"] == "["
    assert result.structured_payload["glob"] == "main/*.txt"
    assert result.structured_payload["matches"] == []
    assert result.structured_payload["scanned_files"] == 0
    assert result.truncated is False
    assert result.externalized is False


@pytest.mark.asyncio
async def test_search_request_cannot_exceed_policy_max_matches(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"alpha {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"search_max_matches": 3}),
    )

    glob_oversized = await tools.glob(pattern="main/*.txt", max_matches=20)
    glob_narrower = await tools.glob(pattern="main/*.txt", max_matches=2)
    grep_oversized = await tools.grep(pattern="alpha", glob="main/*.txt", max_matches=20)
    grep_narrower = await tools.grep(pattern="alpha", glob="main/*.txt", max_matches=2)

    assert glob_oversized.structured_payload["match_limit"] == 3
    assert glob_oversized.structured_payload["returned_matches"] == 3
    assert glob_narrower.structured_payload["match_limit"] == 2
    assert glob_narrower.structured_payload["returned_matches"] == 2
    assert grep_oversized.structured_payload["match_limit"] == 3
    assert grep_oversized.structured_payload["returned_matches"] == 3
    assert grep_narrower.structured_payload["match_limit"] == 2
    assert grep_narrower.structured_payload["returned_matches"] == 2


@pytest.mark.asyncio
async def test_grep_skips_files_over_policy_size_limit(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/large.txt", "alpha\n" + ("x" * 80))
    await sandbox.write_file("/workspace/main/small.txt", "alpha small\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"grep_max_file_bytes": 20}),
    )

    result = await tools.grep(pattern="alpha", glob="main/*.txt")

    assert [item["path"] for item in result.structured_payload["matches"]] == [
        "/workspace/main/small.txt",
    ]
    assert result.structured_payload["skipped_large_files"] == 1
    assert result.structured_payload["scanned_files"] == 1


@pytest.mark.asyncio
async def test_grep_skips_binary_files(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/binary.dat", "alpha\x00binary\n")
    await sandbox.write_file("/workspace/main/text.dat", "alpha text\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_read_policy())

    result = await tools.grep(pattern="alpha", glob="main/*.dat")

    assert [item["path"] for item in result.structured_payload["matches"]] == [
        "/workspace/main/text.dat",
    ]
    assert result.structured_payload["skipped_binary_files"] == 1
    assert result.structured_payload["scanned_files"] == 1


@pytest.mark.asyncio
async def test_grep_skips_lines_over_policy_line_limit(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/lines.txt", f"{'x' * 40} alpha\nalpha short\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_read_policy(output_budget={"grep_max_line_chars": 20}),
    )

    result = await tools.grep(pattern="alpha", glob="main/*.txt")

    assert result.structured_payload["matches"] == [
        {"path": "/workspace/main/lines.txt", "line": 2, "text": "alpha short"},
    ]
    assert result.structured_payload["skipped_long_lines"] == 1


@pytest.mark.asyncio
async def test_protected_paths_are_blocked(sandbox: LocalSandbox) -> None:
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=_write_policy(protected_paths=(".git/**", ".wenjin/env/**", ".env")),
    )

    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.write_file(path="/workspace/.wenjin/env/python/bin/python", content="bad")

    with pytest.raises(HarnessPathError, match="protected path"):
        await tools.read_file(path="/workspace/.env")
