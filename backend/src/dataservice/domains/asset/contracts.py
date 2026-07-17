"""Workspace asset domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.contracts.mission_write_authority import MissionWriteAuthority


class WorkspaceAssetCreateCommand(BaseModel):
    """Register one managed workspace asset."""

    workspace_id: str = Field(min_length=1, max_length=36)
    asset_kind: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    mime_type: str | None = Field(default=None, max_length=100)
    storage_backend: str = Field(default="local", min_length=1, max_length=50)
    storage_path: str = Field(min_length=1, max_length=1000)
    size_bytes: int | None = Field(default=None, ge=0)
    content_hash: str | None = Field(default=None, max_length=128)
    parent_asset_id: str | None = Field(default=None, max_length=36)
    created_by: str = Field(default="system", min_length=1, max_length=100)
    source_kind: str | None = Field(default=None, max_length=50)
    source_id: str | None = Field(default=None, max_length=100)
    mission_write_authority: MissionWriteAuthority | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceAssetUpdateCommand(BaseModel):
    """Update mutable asset metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    mime_type: str | None = Field(default=None, max_length=100)
    metadata_json: dict[str, Any] | None = None


class WorkspaceAssetProjection(BaseModel):
    """Canonical workspace asset projection."""

    id: str
    workspace_id: str
    asset_kind: str
    name: str
    title: str | None = None
    mime_type: str | None = None
    storage_backend: str
    storage_path: str
    size_bytes: int | None = None
    content_hash: str | None = None
    parent_asset_id: str | None = None
    created_by: str
    source_kind: str | None = None
    source_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceAssetDownloadProjection(BaseModel):
    """Storage pointer returned for an authorized download."""

    asset: WorkspaceAssetProjection
    storage_backend: str
    storage_path: str
    mime_type: str | None = None
    filename: str


class WorkspaceArtifactCreateCommand(BaseModel):
    """Create one workspace artifact payload."""

    workspace_id: str = Field(min_length=1, max_length=36)
    artifact_type: str = Field(min_length=1, max_length=100)
    content: dict[str, Any] = Field(default_factory=dict)
    title: str | None = Field(default=None, max_length=500)
    created_by_skill: str | None = Field(default=None, max_length=100)
    parent_artifact_id: str | None = Field(default=None, max_length=36)


class WorkspaceArtifactUpdateCommand(BaseModel):
    """Update mutable workspace artifact payload fields."""

    title: str | None = Field(default=None, max_length=500)
    content: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=20)
    artifact_type: str | None = Field(default=None, max_length=100)
    version: int | None = Field(default=None, ge=1)
    parent_artifact_id: str | None = Field(default=None, max_length=36)


class WorkspaceArtifactProjection(BaseModel):
    """Projection over workspace artifacts owned by DataService."""

    id: str
    workspace_id: str
    type: str
    title: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    created_by_skill: str | None = None
    parent_artifact_id: str | None = None
    version: int = 1
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
