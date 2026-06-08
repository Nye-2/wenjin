"""Bounded context assembly for Wenjin harness-enabled subagents."""

from __future__ import annotations

import json
from typing import Any

from src.sandbox.workspace_layout import (
    build_agent_workspace_contract,
    is_workspace_internal_path,
    is_workspace_protected_path,
)

HARNESS_CONTEXT_BUNDLE_SCHEMA = "wenjin.harness.context_bundle.v1"
_VISIBLE_WORKSPACE_ROOTS = (
    "/workspace/main",
    "/workspace/datasets",
    "/workspace/scripts",
    "/workspace/outputs",
    "/workspace/reports",
)
_MAX_FILE_SUMMARY_ITEMS = 20


def build_harness_context_bundle(
    *,
    workspace_id: str,
    workspace_type: str | None = None,
    task: dict[str, Any] | None = None,
    workspace_data: dict[str, Any] | None = None,
    max_chars: int = 12000,
) -> dict[str, Any]:
    """Build a compact harness context bundle for tool-using workers."""

    budget = max(500, int(max_chars or 12000))
    bundle = {
        "schema": HARNESS_CONTEXT_BUNDLE_SCHEMA,
        "workspace_id": str(workspace_id or ""),
        "workspace_type": str(workspace_type or ""),
        "task": _safe_dict(task or {}),
        "sandbox": _sandbox_contract(workspace_id=workspace_id, workspace_type=workspace_type),
        "workspace_file_summary": _workspace_file_summary(workspace_data or {}),
        "recent_execution_evidence": _recent_execution_evidence(workspace_data or {}),
        "budget": {"max_chars": budget, "truncated": False},
    }
    return _fit_budget(bundle, budget)


def render_harness_context_for_prompt(bundle: dict[str, Any]) -> str:
    """Render the context bundle as deterministic bounded JSON."""

    return json.dumps(bundle, ensure_ascii=False, sort_keys=True)


def _sandbox_contract(*, workspace_id: str, workspace_type: str | None) -> dict[str, Any]:
    contract = build_agent_workspace_contract(
        workspace_id=workspace_id,
        workspace_type=workspace_type or "",
    )
    directories = contract.get("directories")
    directories = directories if isinstance(directories, dict) else {}
    standard_dirs = [
        str(item.get("path"))
        for item in directories.values()
        if isinstance(item, dict)
        and str(item.get("path") or "").startswith("/workspace/")
        and not str(item.get("path") or "").startswith("/workspace/.wenjin")
    ]
    artifact_roots = contract.get("artifact_roots")
    artifact_roots = artifact_roots if isinstance(artifact_roots, dict) else {}
    return {
        "root": str(contract.get("virtual_root") or "/workspace"),
        "standard_dirs": standard_dirs,
        "artifact_roots": [str(path) for path in artifact_roots.values() if str(path).strip()],
        "protected_paths": [str(path) for path in contract.get("protected_paths") or ()],
        "internal_paths": [str(path) for path in contract.get("internal_paths") or ()],
        "rules": [str(rule) for rule in contract.get("rules") or ()],
    }


def _recent_execution_evidence(workspace_data: dict[str, Any]) -> list[dict[str, Any]]:
    history = workspace_data.get("workspace_history")
    history = history if isinstance(history, dict) else {}
    recent = history.get("recent_executions")
    if recent is None:
        recent = workspace_data.get("recent_executions")
    if not isinstance(recent, list):
        return []
    evidence: list[dict[str, Any]] = []
    for item in recent[:8]:
        if not isinstance(item, dict):
            continue
        compact: dict[str, Any] = {}
        _copy_safe_string(compact, "execution_id", item.get("execution_id") or item.get("id"))
        _copy_safe_string(compact, "display_name", item.get("display_name") or item.get("name"))
        _copy_safe_string(compact, "status", item.get("status"))
        _copy_safe_string(compact, "summary", item.get("summary") or item.get("output_preview"))
        harness = _harness_summary(item)
        if harness:
            compact["harness"] = harness
        if compact:
            evidence.append(compact)
    return evidence


def _workspace_file_summary(workspace_data: dict[str, Any]) -> dict[str, Any]:
    raw = workspace_data.get("workspace_file_summary")
    if raw is None:
        raw = workspace_data.get("workspace_files")
    raw = raw if isinstance(raw, dict) else {}
    recent_outputs, outputs_truncated = _safe_file_refs(raw.get("recent_outputs"))
    recent_scripts, scripts_truncated = _safe_file_refs(raw.get("recent_scripts"))
    return {
        "visible_roots": list(_VISIBLE_WORKSPACE_ROOTS),
        "recent_outputs": recent_outputs,
        "recent_scripts": recent_scripts,
        "truncated": outputs_truncated or scripts_truncated,
    }


def _safe_file_refs(value: Any) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(value, list):
        return [], False
    result: list[dict[str, Any]] = []
    for item in value:
        if len(result) >= _MAX_FILE_SUMMARY_ITEMS:
            return result, True
        ref = _safe_file_ref(item)
        if ref:
            result.append(ref)
    return result, False


def _safe_file_ref(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        path = value.strip()
        if not _is_public_workspace_path(path):
            return None
        return {"path": path}
    if not isinstance(value, dict):
        return None
    path = str(value.get("path") or "").strip()
    if not _is_public_workspace_path(path):
        return None
    compact: dict[str, Any] = {"path": path}
    for key in ("kind", "name", "title", "size_bytes", "updated_at"):
        safe = _safe_value(value.get(key))
        if safe not in (None, {}, []):
            compact[key] = safe
    return compact


def _is_public_workspace_path(path: str) -> bool:
    if not path.startswith("/workspace/"):
        return False
    if is_workspace_internal_path(path) or is_workspace_protected_path(path):
        return False
    return any(path == root or path.startswith(f"{root}/") for root in _VISIBLE_WORKSPACE_ROOTS)


def _harness_summary(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("node_metadata")
    metadata = metadata if isinstance(metadata, dict) else item
    harness = metadata.get("harness")
    if not isinstance(harness, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in (
        "file_change_summary",
        "tool_failure_summary",
        "sandbox_execution_summary",
        "reproducibility_summary",
    ):
        value = _safe_value(harness.get(key))
        if value not in (None, {}, []):
            compact[key] = value
    return compact


def _copy_safe_string(target: dict[str, Any], key: str, value: Any) -> None:
    safe = _safe_value(value)
    if isinstance(safe, str) and safe:
        target[key] = safe


def _safe_dict(value: dict[str, Any]) -> dict[str, Any]:
    safe = _safe_value(value)
    return safe if isinstance(safe, dict) else {}


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text or _contains_protected_or_internal_path(text):
            return None
        return text if len(text) <= 500 else f"{text[:497]}..."
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe = _safe_value(item)
            if safe not in (None, {}, []):
                result[str(key)] = safe
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            safe = _safe_value(item)
            if safe not in (None, {}, []):
                result.append(safe)
        return result
    text = str(value).strip()
    if not text or _contains_protected_or_internal_path(text):
        return None
    return text if len(text) <= 500 else f"{text[:497]}..."


def _contains_protected_or_internal_path(text: str) -> bool:
    markers = (
        "/workspace/outputs/harness",
        "/workspace/.wenjin",
        "/workspace/.git",
        "/workspace/.env",
        "/.env",
    )
    return any(marker in text for marker in markers)


def _fit_budget(bundle: dict[str, Any], max_chars: int) -> dict[str, Any]:
    if len(render_harness_context_for_prompt(bundle)) <= max_chars:
        return bundle
    compact = dict(bundle)
    compact["recent_execution_evidence"] = list(bundle.get("recent_execution_evidence") or [])
    while compact["recent_execution_evidence"] and len(render_harness_context_for_prompt(compact)) > max_chars:
        compact["recent_execution_evidence"].pop()
    if len(render_harness_context_for_prompt(compact)) > max_chars:
        compact["workspace_file_summary"] = {
            "visible_roots": [],
            "recent_outputs": [],
            "recent_scripts": [],
            "truncated": True,
        }
    if len(render_harness_context_for_prompt(compact)) > max_chars:
        compact.pop("workspace_file_summary", None)
    if len(render_harness_context_for_prompt(compact)) > max_chars:
        compact["task"] = {}
    compact["budget"] = {"max_chars": max_chars, "truncated": True}
    return compact
