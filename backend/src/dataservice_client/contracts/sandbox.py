"""Sandbox contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SandboxEnvironmentCreatePayload(BaseModel):
    workspace_id: str
    sandbox_id: str | None = None
    provider: str = "docker"
    state: str = "active"
    workspace_path: str | None = None
    network_policy: str = "restricted_egress"
    policy_json: dict[str, Any] = Field(default_factory=dict)
    resource_limits_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "system"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxEnvironmentUpdatePayload(BaseModel):
    state: str | None = None
    workspace_path: str | None = None
    network_policy: str | None = None
    policy_json: dict[str, Any] | None = None
    resource_limits_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class SandboxJobCreatePayload(BaseModel):
    workspace_id: str
    sandbox_environment_id: str
    execution_id: str | None = None
    execution_node_id: str | None = None
    operation: str = "run_python"
    billable: bool = True
    language: str = "python"
    runtime_image: str = "python:3.13-slim"
    command: str
    script_hash: str | None = None
    input_hashes_json: dict[str, Any] = Field(default_factory=dict)
    network_policy: str = "restricted_egress"
    resource_limits_json: dict[str, Any] = Field(default_factory=dict)
    policy_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxJobUpdatePayload(BaseModel):
    status: str
    exit_code: int | None = None
    stdout_asset_id: str | None = None
    stderr_asset_id: str | None = None
    error_text: str | None = None
    metadata_json: dict[str, Any] | None = None


class SandboxArtifactCreatePayload(BaseModel):
    workspace_id: str
    sandbox_job_id: str
    workspace_asset_id: str
    artifact_kind: str
    path: str
    mime_type: str | None = None
    content_hash: str | None = None
    reproducibility_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxLeaseAcquirePayload(BaseModel):
    workspace_id: str
    sandbox_environment_id: str | None = None
    holder_job_id: str
    holder_execution_id: str | None = None
    lease_token: str
    ttl_seconds: int = 900
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SandboxLeaseRenewPayload(BaseModel):
    workspace_id: str
    lease_token: str
    ttl_seconds: int = 900
    metadata_json: dict[str, Any] | None = None


class SandboxLeaseReleasePayload(BaseModel):
    workspace_id: str
    lease_token: str


class SandboxEnvironmentPayload(BaseModel):
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


class SandboxJobPayload(BaseModel):
    id: str
    workspace_id: str
    sandbox_environment_id: str
    execution_id: str | None = None
    execution_node_id: str | None = None
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


class SandboxLeasePayload(BaseModel):
    id: str
    workspace_id: str
    sandbox_environment_id: str | None = None
    holder_job_id: str
    holder_execution_id: str | None = None
    lease_token: str
    expires_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SandboxArtifactPayload(BaseModel):
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
    review_batch_id: str | None = None
    review_item_id: str | None = None
    materialization_status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
