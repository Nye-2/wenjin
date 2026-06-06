from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext
from src.agents.harness.sandbox_tools import (
    HarnessPathError,
    SandboxFileTools,
)
from src.sandbox.providers.local import LocalSandbox


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
        permissions=frozenset({"filesystem.write", "filesystem.diff"}),
        **overrides,
    )


@pytest.mark.asyncio
async def test_read_file_returns_bounded_preview(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "line 1\nline 2\nline 3\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    result = await tools.read_file(path="/workspace/main.tex", start_line=2, end_line=2)

    assert result.structured_payload["path"] == "/workspace/main.tex"
    assert result.preview_text == "line 2\n"
    assert not result.truncated


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
async def test_str_replace_requires_unique_match(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.tex", "same\nsame\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=_write_policy())

    with pytest.raises(ValueError, match="expected exactly one match"):
        await tools.str_replace(path="/workspace/main.tex", old="same", new="changed")


@pytest.mark.asyncio
async def test_grep_and_glob_stay_inside_workspace(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/a.txt", "alpha\n")
    await sandbox.write_file("/workspace/nested/b.txt", "beta alpha\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=HarnessPolicy())

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
