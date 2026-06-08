"""Tool-call attribution helpers for harness node metadata."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from typing import Any

FILE_CHANGE_SUMMARY_SCHEMA = "wenjin.harness.file_change_summary.v1"
TOOL_FAILURE_SUMMARY_SCHEMA = "wenjin.harness.tool_failure_summary.v1"
SANDBOX_EXECUTION_SUMMARY_SCHEMA = "wenjin.harness.sandbox_execution_summary.v1"
REPLAN_SIGNAL_SCHEMA = "wenjin.harness.replan_signal.v1"
RUN_JOURNAL_SUMMARY_SCHEMA = "wenjin.harness.run_journal_summary.v1"
REPRODUCIBILITY_SUMMARY_SCHEMA = "wenjin.harness.reproducibility_summary.v1"


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
    sandbox_execution_summary = build_sandbox_execution_summary_from_tool_calls(tool_calls)
    if sandbox_execution_summary is not None:
        harness["sandbox_execution_summary"] = sandbox_execution_summary
    reproducibility_summary = build_reproducibility_summary_from_tool_calls(tool_calls)
    if reproducibility_summary is not None:
        harness["reproducibility_summary"] = reproducibility_summary
    replan_signals = build_harness_replan_signals_from_tool_calls(tool_calls)
    if replan_signals:
        harness["replan_signals"] = replan_signals
    run_journal_summary = build_run_journal_summary_from_tool_calls(
        tool_calls,
        file_change_summary=file_change_summary,
        tool_failure_summary=tool_failure_summary,
        sandbox_execution_summary=sandbox_execution_summary,
    )
    if run_journal_summary is not None:
        harness["run_journal_summary"] = run_journal_summary
    if not harness:
        return None
    return {"harness": harness}


def build_run_journal_summary_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
    *,
    file_change_summary: dict[str, Any] | None = None,
    tool_failure_summary: dict[str, Any] | None = None,
    sandbox_execution_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the compact member activity line shown in run projections."""

    calls = [tool_call for tool_call in tool_calls or [] if isinstance(tool_call, dict)]
    if not calls:
        return None
    artifact_count = _int_value((sandbox_execution_summary or {}).get("generated_artifact_count"))
    summary = _run_journal_summary_text(
        tool_call_count=len(calls),
        artifact_count=artifact_count,
        file_change_summary=file_change_summary,
        tool_failure_summary=tool_failure_summary,
        sandbox_execution_summary=sandbox_execution_summary,
    )
    return {
        "schema": RUN_JOURNAL_SUMMARY_SCHEMA,
        "latest_phase": "tool_completed",
        "summary": summary,
        "tool_call_count": len(calls),
        "artifact_count": artifact_count,
    }


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


def build_sandbox_execution_summary_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Build a compact summary of sandbox Python execution evidence."""

    if not tool_calls:
        return None

    python_runs = 0
    failed_python_runs = 0
    recoverable_failures = 0
    generated_artifact_count = 0
    sandbox_job_ids: list[str] = []
    sandbox_environment_ids: list[str] = []
    failure_codes: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        name = str(tool_call.get("name") or "").strip()
        if name != "sandbox.run_python":
            continue
        python_runs += 1
        metadata = tool_call.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        manifest = _first_dict(tool_call.get("execution_manifest"), metadata.get("execution_manifest"))
        if manifest is not None:
            _append_unique(sandbox_job_ids, str(manifest.get("sandbox_job_id") or ""))
            _append_unique(sandbox_environment_ids, str(manifest.get("sandbox_environment_id") or ""))
        classification = _first_dict(
            tool_call.get("failure_classification"),
            metadata.get("failure_classification"),
        )
        error_code = str(
            (classification or {}).get("failure_code")
            or tool_call.get("error_code")
            or metadata.get("error_code")
            or ""
        ).strip()
        has_failure = (
            classification is not None
            or str(tool_call.get("status") or "").strip() == "failed"
            or bool(tool_call.get("recoverable_error") or metadata.get("recoverable_error"))
        )
        if has_failure:
            failed_python_runs += 1
        if error_code:
            _append_unique(failure_codes, error_code)
        if _is_recoverable_failure(tool_call, metadata, classification):
            recoverable_failures += 1
        generated_artifact_count += len(_list_of_dicts(tool_call.get("generated_artifacts")))
        generated_artifact_count += len(_list_of_dicts(metadata.get("generated_artifacts")))

    if python_runs == 0:
        return None
    return {
        "schema": SANDBOX_EXECUTION_SUMMARY_SCHEMA,
        "python_runs": python_runs,
        "failed_python_runs": failed_python_runs,
        "recoverable_failures": recoverable_failures,
        "sandbox_job_ids": sandbox_job_ids[:20],
        "sandbox_environment_ids": sandbox_environment_ids[:20],
        "failure_codes": failure_codes[:20],
        "generated_artifact_count": generated_artifact_count,
    }


def build_reproducibility_summary_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Build compact run evidence for experiment reproducibility."""

    if not tool_calls:
        return None

    python_runs = 0
    manifest_count = 0
    script_paths: list[str] = []
    artifact_paths: list[str] = []
    dependency_names: list[str] = []
    dataset_paths: list[str] = []
    sandbox_environment_ids: list[str] = []
    sandbox_job_ids: list[str] = []
    install_job_ids: list[str] = []
    command_risk_levels: list[str] = []
    next_actions: list[str] = []
    narrative_count = 0
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        name = str(tool_call.get("name") or "").strip()
        if name != "sandbox.run_python":
            continue
        python_runs += 1
        metadata = tool_call.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        manifest = _first_dict(
            tool_call.get("reproducibility_manifest"),
            metadata.get("reproducibility_manifest"),
        )
        if manifest is None:
            continue
        manifest_count += 1
        script = manifest.get("script") if isinstance(manifest.get("script"), dict) else {}
        _append_unique(script_paths, str(script.get("path") or ""))
        sandbox = manifest.get("sandbox") if isinstance(manifest.get("sandbox"), dict) else {}
        _append_unique(sandbox_environment_ids, str(sandbox.get("environment_id") or ""))
        _append_unique(sandbox_job_ids, str(sandbox.get("run_job_id") or ""))
        for install_job_id in _list_value(sandbox.get("install_job_ids")):
            _append_unique(install_job_ids, str(install_job_id or ""))
        dependencies = manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}
        for dependency in _list_value(dependencies.get("requested")) + _list_value(dependencies.get("installed")):
            _append_unique(dependency_names, str(dependency or ""))
        for artifact in _list_of_dicts(manifest.get("artifacts")):
            _append_unique(artifact_paths, str(artifact.get("path") or ""))
        command_audit = manifest.get("command_audit") if isinstance(manifest.get("command_audit"), dict) else {}
        _append_unique(command_risk_levels, str(command_audit.get("run_risk_level") or ""))
        for risk_level in _list_value(command_audit.get("install_risk_levels")):
            _append_unique(command_risk_levels, str(risk_level or ""))
        narrative = _first_dict(
            tool_call.get("experiment_narrative"),
            metadata.get("experiment_narrative"),
        )
        if narrative is not None:
            narrative_count += 1
            for dataset_path in _list_value(narrative.get("dataset_paths")):
                _append_unique(dataset_paths, str(dataset_path or ""))
            for artifact_path in _list_value(narrative.get("artifact_paths")):
                _append_unique(artifact_paths, str(artifact_path or ""))
            for dependency in _list_value(narrative.get("dependency_names")):
                _append_unique(dependency_names, str(dependency or ""))
            for action in _list_value(narrative.get("next_actions")):
                _append_unique(next_actions, str(action or ""))

    if python_runs == 0:
        return None
    return {
        "schema": REPRODUCIBILITY_SUMMARY_SCHEMA,
        "python_runs": python_runs,
        "manifest_count": manifest_count,
        "script_paths": script_paths[:20],
        "dataset_paths": dataset_paths[:50],
        "artifact_paths": artifact_paths[:50],
        "dependency_names": dependency_names[:50],
        "sandbox_environment_ids": sandbox_environment_ids[:20],
        "sandbox_job_ids": sandbox_job_ids[:20],
        "install_job_ids": install_job_ids[:20],
        "command_risk_levels": command_risk_levels[:20],
        "narrative_count": narrative_count,
        "next_actions": next_actions[:20],
    }


def build_harness_replan_signals_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Build bounded Lead/TeamKernel replan signals from harness tool records."""

    if not tool_calls:
        return []

    signals: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        failure_codes = _tool_failure_codes(tool_call)
        if "python_exit_nonzero" in failure_codes:
            signals.append(
                _replan_signal(
                    trigger="recoverable_tool_failure",
                    failure_codes=["python_exit_nonzero"],
                    recommended_action="revise_script_or_recruit_code_agent",
                    max_extra_iterations=1,
                )
            )
            continue
        if "sandbox_queue_timeout" in failure_codes:
            signals.append(
                _replan_signal(
                    trigger="sandbox_queue_timeout",
                    failure_codes=["sandbox_queue_timeout"],
                    recommended_action="wait_or_stop",
                    max_extra_iterations=0,
                )
            )
            continue
        if "tool_input_validation" in failure_codes:
            signals.append(
                _replan_signal(
                    trigger="recoverable_tool_input_validation",
                    failure_codes=["tool_input_validation"],
                    recommended_action="revise_tool_call_args",
                    max_extra_iterations=1,
                )
            )
            continue
        if any(code in {"tool_forbidden", "tool_unknown"} for code in failure_codes):
            signals.append(
                _replan_signal(
                    trigger="tool_policy_blocked",
                    failure_codes=[code for code in failure_codes if code in {"tool_forbidden", "tool_unknown"}],
                    recommended_action="revise_policy_or_stop",
                    max_extra_iterations=0,
                )
            )
    return _dedupe_replan_signals(signals)


def _run_journal_summary_text(
    *,
    tool_call_count: int,
    artifact_count: int,
    file_change_summary: dict[str, Any] | None,
    tool_failure_summary: dict[str, Any] | None,
    sandbox_execution_summary: dict[str, Any] | None,
) -> str:
    failed_tools = _int_value((tool_failure_summary or {}).get("total_failed_calls"))
    if failed_tools > 0:
        return "工具异常待处理"
    failed_python_runs = _int_value((sandbox_execution_summary or {}).get("failed_python_runs"))
    if failed_python_runs > 0:
        return "实验需要修订"
    if artifact_count > 0:
        return f"已生成 {artifact_count} 个产物"
    python_runs = _int_value((sandbox_execution_summary or {}).get("python_runs"))
    if python_runs > 0:
        return "已完成实验"
    changed_paths = len(_list_value((file_change_summary or {}).get("changed_paths")))
    if changed_paths > 0:
        return f"已更新 {changed_paths} 个文件"
    return f"完成 {tool_call_count} 次工具调用"


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


def _first_dict(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return value
    return None


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _is_recoverable_failure(
    tool_call: dict[str, Any],
    metadata: dict[str, Any],
    classification: dict[str, Any] | None,
) -> bool:
    if classification is not None and classification.get("recoverable") is True:
        return True
    return bool(tool_call.get("recoverable_error") or metadata.get("recoverable_error"))


def _tool_failure_codes(tool_call: dict[str, Any]) -> list[str]:
    metadata = tool_call.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    classification = _first_dict(
        tool_call.get("failure_classification"),
        metadata.get("failure_classification"),
    )
    values = [
        (classification or {}).get("failure_code"),
        tool_call.get("error_code"),
        metadata.get("error_code"),
    ]
    codes = [str(value).strip() for value in values if str(value or "").strip()]
    error = str(
        tool_call.get("recoverable_error")
        or metadata.get("recoverable_error")
        or tool_call.get("error")
        or ""
    )
    for marker in ("python_exit_nonzero", "sandbox_queue_timeout", "tool_forbidden", "tool_unknown"):
        if marker in error:
            codes.append(marker)
    return _dedupe_strings(codes)


def _replan_signal(
    *,
    trigger: str,
    failure_codes: list[str],
    recommended_action: str,
    max_extra_iterations: int,
) -> dict[str, Any]:
    return {
        "schema": REPLAN_SIGNAL_SCHEMA,
        "trigger": trigger,
        "failure_codes": _dedupe_strings(failure_codes),
        "recommended_action": recommended_action,
        "max_extra_iterations": max(0, int(max_extra_iterations)),
    }


def _dedupe_replan_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for signal in signals:
        key = _replan_signal_key(signal)
        if key in seen:
            continue
        seen.add(key)
        result.append(signal)
    return result


def _replan_signal_key(value: dict[str, Any]) -> str:
    return "|".join(
        [
            str(value.get("trigger") or ""),
            ",".join(_string_list(value.get("failure_codes"))),
            str(value.get("recommended_action") or ""),
        ]
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        _append_unique(result, value)
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _sha256(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
