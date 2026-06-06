from __future__ import annotations

from src.agents.harness.diff_tracker import (
    build_file_change,
    build_file_change_summary_from_tool_calls,
)
from src.agents.harness.loop_guard import HarnessLoopGuard
from src.agents.harness.output_budget import cap_text, select_lines


def test_output_budget_caps_text_and_selects_line_window() -> None:
    content = "line 1\nline 2\nline 3\n"

    assert select_lines(content, start_line=2, end_line=2) == "line 2\n"
    assert cap_text("abcdef", 3) == ("abc", True)
    assert cap_text("abc", 3) == ("abc", False)


def test_diff_tracker_records_hashes_and_unified_diff() -> None:
    change = build_file_change(
        path="/workspace/main.tex",
        before="old\n",
        after="new\n",
        operation="update",
    )

    assert change["path"] == "/workspace/main.tex"
    assert change["operation"] == "update"
    assert change["before_hash"] != change["after_hash"]
    assert "-old" in change["unified_diff"]
    assert "+new" in change["unified_diff"]


def test_file_change_summary_collapses_tool_changes_by_path() -> None:
    first = build_file_change(
        path="/workspace/main.tex",
        before="old\n",
        after="middle\n",
        operation="update",
    )
    second = build_file_change(
        path="/workspace/main.tex",
        before="middle\n",
        after="new\n",
        operation="update",
    )
    added = build_file_change(
        path="/workspace/reports/summary.md",
        before=None,
        after="# Summary\n",
        operation="add",
    )

    summary = build_file_change_summary_from_tool_calls(
        [
            {"name": "sandbox.write_file", "status": "completed", "file_changes": [first]},
            {"name": "sandbox.str_replace", "status": "completed", "file_changes": [second]},
            {"name": "sandbox.write_file", "status": "completed", "file_changes": [added]},
        ]
    )

    assert summary["schema"] == "wenjin.harness.file_change_summary.v1"
    assert summary["changed_count"] == 2
    assert summary["reverted_count"] == 0
    assert summary["paths"] == ["/workspace/main.tex", "/workspace/reports/summary.md"]
    [main_change, report_change] = summary["changes"]
    assert main_change["path"] == "/workspace/main.tex"
    assert main_change["operation"] == "update"
    assert main_change["change_count"] == 2
    assert main_change["before_hash"] == first["before_hash"]
    assert main_change["after_hash"] == second["after_hash"]
    assert len(main_change["diffs"]) == 2
    assert report_change["operation"] == "add"


def test_file_change_summary_does_not_treat_missing_hashes_as_reverted() -> None:
    summary = build_file_change_summary_from_tool_calls(
        [
            {
                "name": "external_sandbox.write_file",
                "status": "completed",
                "file_changes": [
                    {
                        "path": "/workspace/notes.md",
                        "operation": "update",
                        "unified_diff": "",
                    }
                ],
            }
        ]
    )

    assert summary["changed_count"] == 1
    assert summary["reverted_count"] == 0
    assert summary["changes"][0]["operation"] == "update"


def test_loop_guard_warns_then_stops_repeated_identical_tool_calls() -> None:
    guard = HarnessLoopGuard(warn_threshold=3, hard_limit=5)
    args = {"path": "/workspace/main.tex"}

    assert guard.record("sandbox.read_file", args).allowed
    assert guard.record("sandbox.read_file", args).allowed

    warning = guard.record("sandbox.read_file", args)
    assert warning.allowed
    assert warning.should_warn

    assert guard.record("sandbox.read_file", args).allowed
    stopped = guard.record("sandbox.read_file", args)
    assert not stopped.allowed
    assert stopped.stop_reason == "tool_loop_hard_stop"
