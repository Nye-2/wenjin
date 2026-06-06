from __future__ import annotations

from src.agents.harness.diff_tracker import build_file_change
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
