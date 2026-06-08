"""Tool-call attribution helpers for harness node metadata."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from typing import Any

FILE_CHANGE_SUMMARY_SCHEMA = "wenjin.harness.file_change_summary.v1"
TOOL_FAILURE_SUMMARY_SCHEMA = "wenjin.harness.tool_failure_summary.v1"


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

    harness: dict[str, Any] = {}
    file_change_summary = build_file_change_summary_from_tool_calls(tool_calls)
    if file_change_summary is not None:
        harness["file_change_summary"] = file_change_summary
    tool_failure_summary = build_tool_failure_summary_from_tool_calls(tool_calls)
    if tool_failure_summary is not None:
        harness["tool_failure_summary"] = tool_failure_summary
    if not harness:
        return None
    return {"harness": harness}


def build_tool_failure_summary_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Build a compact summary of failed and recoverable harness tool calls."""

    if not tool_calls:
        return None

    failures: list[dict[str, Any]] = []
    failed_tools: list[str] = []
    recoverable_error_codes: list[str] = []
    total_recoverable_errors = 0
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        status = str(tool_call.get("status") or "").strip()
        metadata = tool_call.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        recoverable_error = str(metadata.get("recoverable_error") or "").strip()
        error = str(tool_call.get("error") or recoverable_error).strip()
        if recoverable_error:
            total_recoverable_errors += 1
        if status != "failed":
            if recoverable_error:
                _append_unique(recoverable_error_codes, str(metadata.get("error_code") or "recoverable_error"))
            continue
        name = str(tool_call.get("name") or "unknown_tool").strip() or "unknown_tool"
        error_code = str(metadata.get("error_code") or "tool_error").strip() or "tool_error"
        _append_unique(failed_tools, name)
        _append_unique(recoverable_error_codes, error_code)
        failures.append(
            {
                "name": name,
                "status": status,
                "error": _compact_error(error or "tool failed"),
                "error_code": error_code,
                "recoverable": bool(recoverable_error),
                "args": _compact_args(tool_call.get("args")),
            }
        )

    if not failures and total_recoverable_errors == 0:
        return None

    return {
        "schema": TOOL_FAILURE_SUMMARY_SCHEMA,
        "total_failed_calls": len(failures),
        "total_recoverable_errors": total_recoverable_errors,
        "failed_tools": failed_tools,
        "recoverable_error_codes": recoverable_error_codes,
        "failures": failures,
    }


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
    diff = {
        "operation": str(change.get("operation") or ""),
        "before_hash": change.get("before_hash"),
        "after_hash": change.get("after_hash"),
        "unified_diff": str(change.get("unified_diff") or ""),
    }
    output_refs = change.get("diff_output_refs")
    if isinstance(output_refs, list):
        refs = [str(ref) for ref in output_refs if str(ref).strip()]
        if refs:
            diff["diff_output_refs"] = refs
    for key in ("diff_externalized", "diff_truncated"):
        value = change.get(key)
        if isinstance(value, bool):
            diff[key] = value
    return diff


def _compact_args(raw_args: Any) -> dict[str, Any]:
    if not isinstance(raw_args, dict):
        return {}
    compact: dict[str, Any] = {}
    for key, value in raw_args.items():
        name = str(key)
        if isinstance(value, str):
            compact[name] = value if len(value) <= 500 else f"{value[:497]}..."
        elif isinstance(value, int | float | bool) or value is None:
            compact[name] = value
        else:
            text = str(value)
            compact[name] = text if len(text) <= 500 else f"{text[:497]}..."
    return compact


def _compact_error(error: str) -> str:
    text = str(error or "").strip()
    return text if len(text) <= 500 else f"{text[:497]}..."


def _append_unique(values: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _sha256(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
