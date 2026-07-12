"""Sandbox projection helpers."""

from __future__ import annotations

from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactProjection,
    SandboxEnvironmentProjection,
    SandboxJobProjection,
    SandboxLeaseProjection,
)
from src.dataservice.domains.sandbox.models import (
    SandboxArtifactRecord,
    SandboxEnvironmentRecord,
    SandboxJobRecord,
    SandboxLeaseRecord,
)


def environment_to_projection(record: SandboxEnvironmentRecord) -> SandboxEnvironmentProjection:
    return SandboxEnvironmentProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        sandbox_id=record.sandbox_id,
        provider=record.provider,
        state=record.state,
        workspace_path=record.workspace_path,
        network_policy=record.network_policy,
        policy_json=dict(record.policy_json or {}),
        resource_limits_json=dict(record.resource_limits_json or {}),
        created_by=record.created_by,
        last_active_at=record.last_active_at,
        released_at=record.released_at,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def job_to_projection(record: SandboxJobRecord) -> SandboxJobProjection:
    return SandboxJobProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        sandbox_environment_id=str(record.sandbox_environment_id),
        mission_id=record.mission_id,
        mission_item_seq=record.mission_item_seq,
        operation=getattr(record, "operation", "run_python"),
        billable=bool(getattr(record, "billable", True)),
        language=record.language,
        runtime_image=record.runtime_image,
        command=record.command,
        script_hash=record.script_hash,
        input_hashes_json=dict(record.input_hashes_json or {}),
        network_policy=record.network_policy,
        resource_limits_json=dict(record.resource_limits_json or {}),
        policy_json=dict(record.policy_json or {}),
        status=record.status,
        exit_code=record.exit_code,
        stdout_asset_id=record.stdout_asset_id,
        stderr_asset_id=record.stderr_asset_id,
        started_at=record.started_at,
        finished_at=record.finished_at,
        error_text=record.error_text,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def lease_to_projection(record: SandboxLeaseRecord) -> SandboxLeaseProjection:
    return SandboxLeaseProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        sandbox_environment_id=str(record.sandbox_environment_id) if record.sandbox_environment_id else None,
        holder_job_id=str(record.holder_job_id),
        holder_mission_id=str(record.holder_mission_id) if record.holder_mission_id else None,
        lease_token=record.lease_token,
        expires_at=record.expires_at,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def artifact_to_projection(record: SandboxArtifactRecord) -> SandboxArtifactProjection:
    return SandboxArtifactProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        sandbox_environment_id=str(record.sandbox_environment_id),
        sandbox_job_id=str(record.sandbox_job_id),
        workspace_asset_id=str(record.workspace_asset_id),
        artifact_kind=record.artifact_kind,
        path=record.path,
        mime_type=record.mime_type,
        content_hash=record.content_hash,
        reproducibility_json=dict(record.reproducibility_json or {}),
        mission_commit_id=record.mission_commit_id,
        materialization_status=record.materialization_status,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
