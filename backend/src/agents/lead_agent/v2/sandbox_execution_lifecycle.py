"""Bounded execution lifecycle envelopes for Lead-owned sandbox jobs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from src.sandbox.workspace_layout import (
    is_user_reviewable_workspace_artifact_path,
    is_workspace_readable_internal_output_ref,
)

SANDBOX_EXECUTION_LIFECYCLE_SCHEMA = "wenjin.sandbox.execution_lifecycle.v1"


def build_sandbox_execution_lifecycle(
    *,
    status: str,
    operation: str,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    environment_id: str,
    runtime_image: str,
    provider_image: str | None,
    command_preview: str,
    command_argv: Iterable[str],
    cwd: str | None,
    env: Mapping[str, Any] | None,
    network_profile: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Return a model-safe lifecycle envelope without raw stdout, stderr, or source."""

    return {
        "schema": SANDBOX_EXECUTION_LIFECYCLE_SCHEMA,
        "status": _safe_text(status),
        "operation": _safe_text(operation),
        "execution": {
            "workspace_id": _safe_text(workspace_id),
            "execution_id": _safe_text(execution_id),
            "node_id": _safe_text(node_id),
        },
        "sandbox": {
            "environment_id": _safe_text(environment_id),
            "runtime_image": _safe_text(runtime_image),
            "provider_image": _safe_text(provider_image),
        },
        "command": {
            "preview": _safe_text(command_preview, limit=500),
            "argv": [_safe_text(item, limit=300) for item in command_argv if _safe_text(item)],
            "cwd": _safe_text(cwd),
            "env_keys": sorted(_safe_text(key, limit=120) for key in (env or {}).keys() if _safe_text(key)),
            "network_profile": _safe_text(network_profile),
            "timeout_seconds": _positive_int(timeout_seconds),
        },
    }


def finalize_sandbox_execution_lifecycle(
    lifecycle: Mapping[str, Any],
    *,
    sandbox_job_id: str,
    status: str,
    exit_code: int | None,
    stdout_externalized: bool,
    stderr_externalized: bool,
    output_refs: Iterable[str],
    generated_artifacts: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Return a terminal lifecycle envelope with bounded output metadata only."""

    finalized = deepcopy(dict(lifecycle))
    finalized["status"] = _safe_text(status)
    finalized["sandbox_job_id"] = _safe_text(sandbox_job_id)
    finalized["exit_code"] = _int_or_none(exit_code)
    finalized["outputs"] = {
        "stdout_externalized": bool(stdout_externalized),
        "stderr_externalized": bool(stderr_externalized),
        "output_refs": _safe_output_refs(output_refs),
        "generated_artifact_count": _reviewable_artifact_count(generated_artifacts),
    }
    return finalized


def _safe_output_refs(output_refs: Iterable[str]) -> list[str]:
    refs: list[str] = []
    for ref in output_refs:
        text = _safe_text(ref, limit=500)
        if text and is_workspace_readable_internal_output_ref(text) and text not in refs:
            refs.append(text)
    return refs


def _reviewable_artifact_count(generated_artifacts: Iterable[Mapping[str, Any]] | None) -> int:
    total = 0
    for artifact in generated_artifacts or []:
        if not isinstance(artifact, Mapping):
            continue
        path = _safe_text(artifact.get("path"), limit=500)
        if is_user_reviewable_workspace_artifact_path(path):
            total += 1
    return total


def _safe_text(value: Any, *, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text)} chars)"


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
