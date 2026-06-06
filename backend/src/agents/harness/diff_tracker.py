"""File-change attribution helpers for harness write tools."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from typing import Any

FILE_CHANGE_SUMMARY_SCHEMA = "wenjin.harness.file_change_summary.v1"


def build_file_change(
    *,
    path: str,
    before: str | None,
    after: str,
    operation: str,
) -> dict[str, Any]:
    """Build the compact file-change record stored with harness tool calls."""

    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff = "".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path.removeprefix('/')}",
            tofile=f"b/{path.removeprefix('/')}",
        )
    )
    return {
        "path": path,
        "operation": operation,
        "before_hash": _sha256(before),
        "after_hash": _sha256(after),
        "unified_diff": diff,
    }


def build_file_change_summary_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Build a path-level net summary from per-tool harness file changes."""

    if not tool_calls:
        return None

    by_path: dict[str, dict[str, Any]] = {}
    paths: list[str] = []
    total_changes = 0
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        file_changes = tool_call.get("file_changes")
        if not isinstance(file_changes, list):
            continue
        for raw_change in file_changes:
            if not isinstance(raw_change, dict):
                continue
            path = str(raw_change.get("path") or "").strip()
            if not path:
                continue
            total_changes += 1
            if path not in by_path:
                paths.append(path)
                by_path[path] = _new_path_summary(path, raw_change)
                continue
            _merge_path_summary(by_path[path], raw_change)

    if not by_path:
        return None

    changes = [_finalize_path_summary(by_path[path]) for path in paths]
    reverted = [change for change in changes if change["operation"] == "reverted"]
    changed = [change for change in changes if change["operation"] != "reverted"]
    return {
        "schema": FILE_CHANGE_SUMMARY_SCHEMA,
        "total_tool_changes": total_changes,
        "changed_count": len(changed),
        "reverted_count": len(reverted),
        "paths": [change["path"] for change in changes],
        "changed_paths": [change["path"] for change in changed],
        "reverted_paths": [change["path"] for change in reverted],
        "changes": changes,
    }


def build_harness_node_metadata_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Build execution-node metadata for harness tool activity."""

    file_change_summary = build_file_change_summary_from_tool_calls(tool_calls)
    if file_change_summary is None:
        return None
    return {"harness": {"file_change_summary": file_change_summary}}


def _new_path_summary(path: str, change: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": path,
        "before_hash": change.get("before_hash"),
        "after_hash": change.get("after_hash"),
        "first_operation": str(change.get("operation") or ""),
        "last_operation": str(change.get("operation") or ""),
        "change_count": 1,
        "diffs": [_compact_diff(change)],
    }


def _merge_path_summary(summary: dict[str, Any], change: dict[str, Any]) -> None:
    summary["after_hash"] = change.get("after_hash")
    summary["last_operation"] = str(change.get("operation") or "")
    summary["change_count"] = int(summary.get("change_count") or 0) + 1
    summary["diffs"].append(_compact_diff(change))


def _finalize_path_summary(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary)
    result["operation"] = _net_operation(result)
    return result


def _net_operation(summary: dict[str, Any]) -> str:
    before_hash = summary.get("before_hash")
    after_hash = summary.get("after_hash")
    if before_hash is not None and after_hash is not None and before_hash == after_hash:
        return "reverted"
    if before_hash is None and after_hash is not None:
        return "add"
    if before_hash is not None and after_hash is None:
        return "delete"
    last_operation = str(summary.get("last_operation") or "")
    if last_operation in {"add", "update", "delete"}:
        return last_operation
    return "update"


def _compact_diff(change: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": str(change.get("operation") or ""),
        "before_hash": change.get("before_hash"),
        "after_hash": change.get("after_hash"),
        "unified_diff": str(change.get("unified_diff") or ""),
    }


def _sha256(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
