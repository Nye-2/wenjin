"""Sandbox artifact review staging helpers for LeadAgentRuntime."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from src.agents.lead_agent.v2.sandbox_artifact_discovery import DISCOVERY_SCHEMA
from src.dataservice_client.contracts.asset import WorkspaceAssetCreatePayload
from src.dataservice_client.contracts.sandbox import SandboxArtifactCreatePayload
from src.sandbox.workspace_layout import (
    is_user_reviewable_workspace_artifact_path,
    normalize_workspace_virtual_path,
    workspace_artifact_root_for_path,
)

REVIEW_TARGET_DOMAIN = "sandbox"
REVIEW_TARGET_KIND = "sandbox_artifact"


def collect_sandbox_artifact_candidates(node_results: Any) -> list[dict[str, Any]]:
    """Collect generated sandbox artifact candidates from node tool records."""

    if not isinstance(node_results, dict):
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for task_name, node_result in node_results.items():
        if not isinstance(node_result, dict):
            continue
        for tool_call in node_result.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            if tool_call.get("status") != "completed":
                continue
            for artifact in tool_call.get("generated_artifacts") or []:
                candidate = normalize_sandbox_artifact_candidate(
                    artifact,
                    source_task_id=str(task_name),
                )
                if candidate is None:
                    continue
                key = (
                    candidate["sandbox_job_id"],
                    candidate["path"],
                    candidate.get("content_hash"),
                )
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
    return candidates


def normalize_sandbox_artifact_candidate(
    artifact: Any,
    *,
    source_task_id: str,
) -> dict[str, Any] | None:
    """Validate and normalize one generated artifact candidate."""

    if not isinstance(artifact, dict):
        return None
    if artifact.get("schema") != DISCOVERY_SCHEMA:
        return None
    if artifact.get("review_surface") != REVIEW_TARGET_KIND:
        return None
    if artifact.get("materialization_status") != "candidate":
        return None

    path = _clean_text(artifact.get("path"))
    sandbox_job_id = _clean_text(artifact.get("sandbox_job_id"))
    if not path or not sandbox_job_id:
        return None
    try:
        path = normalize_workspace_virtual_path(path)
    except ValueError:
        return None
    if not is_user_reviewable_workspace_artifact_path(path):
        return None

    artifact_kind = _clean_text(artifact.get("artifact_kind")) or _artifact_kind_for_path(path)
    size = _coerce_size(artifact.get("size"))
    return {
        "schema": DISCOVERY_SCHEMA,
        "path": path,
        "root": _clean_text(artifact.get("root")) or _root_name_for_path(path),
        "artifact_kind": artifact_kind[:50],
        "mime_type": _clean_text(artifact.get("mime_type")) or "application/octet-stream",
        "size": size,
        "content_hash": _clean_text(artifact.get("content_hash")),
        "sandbox_job_id": sandbox_job_id,
        "sandbox_environment_id": _clean_text(artifact.get("sandbox_environment_id")),
        "source_task_id": source_task_id,
        "review_surface": REVIEW_TARGET_KIND,
        "materialization_status": "candidate",
    }


def workspace_asset_payload_for_candidate(
    *,
    workspace_id: str,
    execution_id: str,
    candidate: dict[str, Any],
) -> WorkspaceAssetCreatePayload:
    """Build the DataService workspace asset payload for a sandbox artifact."""

    path = candidate["path"]
    return WorkspaceAssetCreatePayload(
        workspace_id=workspace_id,
        asset_kind=candidate["artifact_kind"],
        name=PurePosixPath(path).name or "sandbox-artifact",
        title=PurePosixPath(path).name or path,
        mime_type=candidate.get("mime_type"),
        storage_backend="sandbox",
        storage_path=path,
        size_bytes=candidate.get("size"),
        content_hash=candidate.get("content_hash"),
        created_by=f"execution:{execution_id}",
        source_kind="sandbox_job",
        source_id=candidate["sandbox_job_id"],
        metadata_json=_candidate_metadata(candidate, execution_id=execution_id),
    )


def sandbox_artifact_payload_for_candidate(
    *,
    workspace_id: str,
    execution_id: str,
    workspace_asset_id: str,
    candidate: dict[str, Any],
) -> SandboxArtifactCreatePayload:
    """Build the DataService sandbox artifact payload for a candidate."""

    metadata = _candidate_metadata(candidate, execution_id=execution_id)
    return SandboxArtifactCreatePayload(
        workspace_id=workspace_id,
        sandbox_job_id=candidate["sandbox_job_id"],
        workspace_asset_id=workspace_asset_id,
        artifact_kind=candidate["artifact_kind"],
        path=candidate["path"],
        mime_type=candidate.get("mime_type"),
        content_hash=candidate.get("content_hash"),
        reproducibility_json={
            "source_execution_id": execution_id,
            "source_task_id": candidate.get("source_task_id"),
            "sandbox_environment_id": candidate.get("sandbox_environment_id"),
            "root": candidate.get("root"),
        },
        metadata_json=metadata,
    )


def sandbox_review_item_projection(
    item: Any,
    *,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Project a canonical sandbox ReviewItem into result-card review_items."""

    target_ref = _dict(getattr(item, "target_ref_json", None))
    payload = _dict(getattr(item, "payload_json", None))
    preview = _dict(getattr(item, "preview_json", None))
    provenance = _dict(getattr(item, "provenance_json", None))
    status = str(getattr(item, "status", "pending") or "pending")
    actions: list[dict[str, str]] = []
    if status in {"pending", "accepted"}:
        actions = [
            {"action": "accept_sandbox_artifact", "label": "保存到产物库"},
            {"action": "reject_sandbox_artifact", "label": "忽略"},
        ]
    return {
        "id": str(getattr(item, "id", "")),
        "kind": REVIEW_TARGET_KIND,
        "status": status,
        "title": str(getattr(item, "title", None) or payload.get("path") or "Sandbox artifact"),
        "summary": str(getattr(item, "summary", None) or payload.get("path") or ""),
        "source": {
            "type": provenance.get("source_kind") or "sandbox_job",
            "execution_id": provenance.get("execution_id") or execution_id,
            "job_id": provenance.get("source_id"),
        },
        "target": {
            "kind": REVIEW_TARGET_KIND,
            "path": payload.get("path") or preview.get("path"),
            "artifact_kind": payload.get("artifact_kind"),
            "asset_id": target_ref.get("workspace_asset_id") or payload.get("workspace_asset_id"),
            "sandbox_artifact_id": target_ref.get("sandbox_artifact_id")
            or payload.get("sandbox_artifact_id"),
        },
        "preview": {
            "mode": "artifact",
            "path": preview.get("path") or payload.get("path"),
            "mime_type": preview.get("mime_type"),
            "content_hash": preview.get("content_hash"),
        },
        "actions": actions,
        "created_at": _timestamp(getattr(item, "created_at", None)),
        "updated_at": _timestamp(getattr(item, "updated_at", None)),
        "applied_at": _timestamp(getattr(item, "applied_at", None)),
    }


def _candidate_metadata(candidate: dict[str, Any], *, execution_id: str) -> dict[str, Any]:
    metadata = {
        "schema": candidate["schema"],
        "root": candidate.get("root"),
        "source_execution_id": execution_id,
        "source_task_id": candidate.get("source_task_id"),
        "sandbox_environment_id": candidate.get("sandbox_environment_id"),
        "review_surface": REVIEW_TARGET_KIND,
        "materialization_status": "candidate",
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _root_name_for_path(path: str) -> str:
    root = workspace_artifact_root_for_path(path)
    return root["name"] if root else "outputs"


def _artifact_kind_for_path(path: str) -> str:
    root = workspace_artifact_root_for_path(path)
    return root["artifact_kind"] if root else "sandbox_output"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_size(value: Any) -> int | None:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return max(size, 0)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if value else None
