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
from src.sandbox.workspace_layout import WORKSPACE_PROTECTED_PATHS


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
async def test_read_file_externalizes_large_selected_output(sandbox: LocalSandbox) -> None:
    content = "".join(f"line {index:03d}: {'x' * 20}\n" for index in range(1, 31))
    await sandbox.write_file("/workspace/main/large.txt", content)
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=HarnessPolicy(
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
        policy=HarnessPolicy(output_budget={"externalize_above_chars": 100}),
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
        policy=HarnessPolicy(
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
        policy=HarnessPolicy(
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
async def test_listing_and_search_hide_protected_and_internal_paths(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main/visible.txt", "alpha visible\n")
    await sandbox.write_file("/workspace/outputs/result.txt", "alpha artifact\n")
    await sandbox.write_file("/workspace/.env", "alpha secret\n")
    await sandbox.write_file("/workspace/.wenjin/env/python/bin/python", "alpha runtime\n")
    await sandbox.write_file("/workspace/outputs/harness/exec/node/tool.txt", "alpha internal\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=HarnessPolicy(protected_paths=WORKSPACE_PROTECTED_PATHS),
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
    assert all(not path.startswith("/workspace/.wenjin/env") for path in listed_paths)
    assert all(not path.startswith("/workspace/outputs/harness") for path in listed_paths)
    assert all(not path.startswith("/workspace/.env") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/.wenjin/env") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/outputs/harness") for path in glob_result.structured_payload["matches"])
    assert all(not path.startswith("/workspace/.env") for path in searched_paths)
    assert all(not path.startswith("/workspace/.wenjin/env") for path in searched_paths)
    assert all(not path.startswith("/workspace/outputs/harness") for path in searched_paths)


@pytest.mark.asyncio
async def test_list_dir_accepts_current_virtual_workspace_root(sandbox: LocalSandbox) -> None:
    await sandbox.write_file("/workspace/main.py", "print('ok')\n")
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=HarnessPolicy())

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
        policy=HarnessPolicy(output_budget={"search_max_matches": 5}),
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
        policy=HarnessPolicy(output_budget={"search_max_matches": 5}),
    )

    result = await tools.glob(pattern="main/*.txt")

    assert result.truncated
    assert result.structured_payload["match_limit"] == 5
    assert result.structured_payload["returned_matches"] == 5
    assert len(result.structured_payload["matches"]) == 5
    assert len(result.preview_text.splitlines()) == 5


@pytest.mark.asyncio
async def test_grep_reports_returned_matches_and_limit(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"alpha {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=HarnessPolicy(output_budget={"search_max_matches": 5}),
    )

    result = await tools.grep(pattern="alpha", glob="main/*.txt")

    assert result.truncated
    assert result.structured_payload["match_limit"] == 5
    assert result.structured_payload["returned_matches"] == 5
    assert len(result.structured_payload["matches"]) == 5
    assert len(result.preview_text.splitlines()) == 5


@pytest.mark.asyncio
async def test_search_request_cannot_exceed_policy_max_matches(sandbox: LocalSandbox) -> None:
    for index in range(1, 9):
        await sandbox.write_file(f"/workspace/main/file_{index:02d}.txt", f"alpha {index}\n")
    tools = SandboxFileTools(
        sandbox=sandbox,
        context=_ctx(),
        policy=HarnessPolicy(output_budget={"search_max_matches": 3}),
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
        policy=HarnessPolicy(output_budget={"grep_max_file_bytes": 20}),
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
    tools = SandboxFileTools(sandbox=sandbox, context=_ctx(), policy=HarnessPolicy())

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
        policy=HarnessPolicy(output_budget={"grep_max_line_chars": 20}),
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
