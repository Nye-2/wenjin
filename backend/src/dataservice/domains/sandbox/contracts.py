"""Sandbox domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def default_sandbox_policy() -> dict[str, Any]:
    """Return the standard policy snapshot for Python sandbox jobs."""

    return {
        "schema_version": "sandbox_policy.v1",
        "allow_python": True,
        "allow_network_egress": True,
        "allow_package_install": True,
        "allow_llm_api": True,
        "allow_web_data_fetch": True,
        "allow_workspace_file_io": True,
        "allow_host_network": False,
        "allow_privileged": False,
        "allow_docker_socket": False,
        "allow_host_path_mounts": False,
        "allow_sibling_container_access": False,
        "allow_server_control": False,
    }


def default_resource_limits() -> dict[str, Any]:
    """Return conservative default sandbox resource limits."""

    return {
        "cpu_count": 2,
        "memory_mb": 4096,
        "timeout_seconds": 300,
        "max_output_bytes": 20_000_000,
    }


class SandboxEnvironmentCreateCommand(BaseModel):
    """Create one workspace sandbox environment record."""

    workspace_id: str = Field(min_length=1, max_length=36)
    sandbox_id: str | None = Field(default=None, max_length=100)
    provider: str = Field(default="docker", min_length=1, max_length=50)
    state: str = Field(default="active", pattern="^(active|stopped|error)$")
    workspace_path: str | None = None
    network_policy: str = Field(default="restricted_egress", min_length=1, max_length=50)
    policy_json: dict[str, Any] = Field(default_factory=default_sandbox_policy)
    resource_limits_json: dict[str, Any] = Field(default_factory=default_resource_limits)
    created_by: str = Field(default="system", min_length=1, max_length=100)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxEnvironmentUpdateCommand(BaseModel):
    """Update mutable sandbox environment state."""

    state: str | None = Field(default=None, pattern="^(active|stopped|error)$")
    workspace_path: str | None = None
    network_policy: str | None = Field(default=None, max_length=50)
    policy_json: dict[str, Any] | None = None
    resource_limits_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class SandboxJobCreateCommand(BaseModel):
    """Record one Python sandbox job before execution starts."""

    workspace_id: str = Field(min_length=1, max_length=36)
    sandbox_environment_id: str = Field(min_length=1, max_length=36)
    mission_id: str | None = Field(default=None, max_length=36)
    mission_item_seq: int | None = Field(default=None, ge=1)
    operation: str = Field(default="run_python", pattern="^(run_python|smoke_check|install_dependencies)$")
    billable: bool = True
    language: str = Field(default="python", pattern="^python$")
    runtime_image: str = Field(default="python:3.13-slim", min_length=1, max_length=255)
    command: str = Field(min_length=1)
    script_hash: str | None = Field(default=None, max_length=128)
    input_hashes_json: dict[str, Any] = Field(default_factory=dict)
    network_policy: str = Field(default="restricted_egress", min_length=1, max_length=50)
    resource_limits_json: dict[str, Any] = Field(default_factory=default_resource_limits)
    policy_json: dict[str, Any] = Field(default_factory=default_sandbox_policy)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxJobUpdateCommand(BaseModel):
    """Update execution status for one sandbox job."""

    status: str = Field(pattern="^(queued|running|succeeded|failed|cancelled)$")
    exit_code: int | None = None
    stdout_asset_id: str | None = Field(default=None, max_length=36)
    stderr_asset_id: str | None = Field(default=None, max_length=36)
    error_text: str | None = None
    metadata_json: dict[str, Any] | None = None


class SandboxArtifactCreateCommand(BaseModel):
    """Register one artifact produced by a sandbox job."""

    workspace_id: str = Field(min_length=1, max_length=36)
    sandbox_job_id: str = Field(min_length=1, max_length=36)
    workspace_asset_id: str = Field(min_length=1, max_length=36)
    artifact_kind: str = Field(min_length=1, max_length=50)
    path: str = Field(min_length=1)
    mime_type: str | None = Field(default=None, max_length=100)
    content_hash: str | None = Field(default=None, max_length=128)
    reproducibility_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxLeaseAcquireCommand(BaseModel):
    """Acquire or renew the cross-worker lease for one workspace sandbox."""

    workspace_id: str = Field(min_length=1, max_length=36)
    sandbox_environment_id: str | None = Field(default=None, max_length=36)
    holder_job_id: str = Field(min_length=1, max_length=36)
    holder_mission_id: str | None = Field(default=None, max_length=36)
    lease_token: str = Field(min_length=1, max_length=100)
    ttl_seconds: int = Field(default=900, ge=1, le=86_400)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxLeaseRenewCommand(BaseModel):
    """Renew a workspace sandbox lease held by the same token."""

    workspace_id: str = Field(min_length=1, max_length=36)
    lease_token: str = Field(min_length=1, max_length=100)
    ttl_seconds: int = Field(default=900, ge=1, le=86_400)
    metadata_json: dict[str, Any] | None = None


class SandboxLeaseReleaseCommand(BaseModel):
    """Release a workspace sandbox lease if the token still owns it."""

    workspace_id: str = Field(min_length=1, max_length=36)
    lease_token: str = Field(min_length=1, max_length=100)


class SandboxEnvironmentProjection(BaseModel):
    """Canonical sandbox environment projection."""

    id: str
    workspace_id: str
    sandbox_id: str
    provider: str
    state: str
    workspace_path: str | None = None
    network_policy: str
    policy_json: dict[str, Any] = Field(default_factory=dict)
    resource_limits_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    last_active_at: datetime | None = None
    released_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SandboxJobProjection(BaseModel):
    """Canonical sandbox job projection."""

    id: str
    workspace_id: str
    sandbox_environment_id: str
    mission_id: str | None = None
    mission_item_seq: int | None = None
    operation: str = "run_python"
    billable: bool = True
    language: str
    runtime_image: str
    command: str
    script_hash: str | None = None
    input_hashes_json: dict[str, Any] = Field(default_factory=dict)
    network_policy: str
    resource_limits_json: dict[str, Any] = Field(default_factory=dict)
    policy_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    exit_code: int | None = None
    stdout_asset_id: str | None = None
    stderr_asset_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_text: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SandboxLeaseProjection(BaseModel):
    """Canonical workspace sandbox lease projection."""

    id: str
    workspace_id: str
    sandbox_environment_id: str | None = None
    holder_job_id: str
    holder_mission_id: str | None = None
    lease_token: str
    expires_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SandboxArtifactProjection(BaseModel):
    """Canonical sandbox artifact projection."""

    id: str
    workspace_id: str
    sandbox_environment_id: str
    sandbox_job_id: str
    workspace_asset_id: str
    artifact_kind: str
    path: str
    mime_type: str | None = None
    content_hash: str | None = None
    reproducibility_json: dict[str, Any] = Field(default_factory=dict)
    mission_commit_id: str | None = None
    materialization_status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
