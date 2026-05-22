"""Asset contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceAssetCreatePayload(BaseModel):
    workspace_id: str
    asset_kind: str
    name: str
    title: str | None = None
    mime_type: str | None = None
    storage_backend: str = "local"
    storage_path: str
    size_bytes: int | None = None
    content_hash: str | None = None
    parent_asset_id: str | None = None
    created_by: str = "system"
    source_kind: str | None = None
    source_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceAssetUpdatePayload(BaseModel):
    name: str | None = None
    title: str | None = None
    mime_type: str | None = None
    metadata_json: dict[str, Any] | None = None


class WorkspaceAssetPayload(BaseModel):
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


class WorkspaceAssetDownloadPayload(BaseModel):
    asset: WorkspaceAssetPayload
    storage_backend: str
    storage_path: str
    mime_type: str | None = None
    filename: str


class LegacyArtifactCreatePayload(BaseModel):
    workspace_id: str
    artifact_type: str
    content: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    created_by_skill: str | None = None
    parent_artifact_id: str | None = None


class LegacyArtifactUpdatePayload(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None
    status: str | None = None
    artifact_type: str | None = None
    version: int | None = None
    parent_artifact_id: str | None = None


class LegacyArtifactPayload(BaseModel):
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
