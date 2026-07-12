"""Prism contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PrismPrimaryProjectPayload(BaseModel):
    workspace_id: str
    title: str
    adapter_kind: str = "latex"
    adapter_ref_id: str | None = None
    main_file: str = "main.tex"
    settings_json: dict[str, Any] = Field(default_factory=dict)
    adapter_metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismFileVersionCreatePayload(BaseModel):
    file_id: str
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str = "system"


class PrismWorkspaceFileUpsertPayload(BaseModel):
    path: str
    file_role: str = "generated"
    mime_type: str | None = None
    sort_order: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str | None = None
    created_by: str = "system"
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None


class PrismFileContentUpdatePayload(BaseModel):
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str = "user"
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None
    expected_current_hash: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismFileRestorePayload(BaseModel):
    version_id: str
    expected_current_hash: str | None = None
    created_by: str = "system"


class PrismProtectedScopeUpsertPayload(BaseModel):
    workspace_id: str
    latex_project_id: str
    file_path: str
    section_key: str = ""
    scope: str
    reason: str | None = None
    source: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismProjectPayload(BaseModel):
    id: str
    workspace_id: str
    role: str
    title: str
    adapter_kind: str
    adapter_ref_id: str | None = None
    status: str
    settings_json: dict[str, Any] = Field(default_factory=dict)
    adapter_metadata_json: dict[str, Any] = Field(default_factory=dict)
    trashed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismDocumentPayload(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    document_kind: str
    title: str
    adapter_kind: str
    status: str
    root_file_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismFilePayload(BaseModel):
    id: str
    workspace_id: str
    document_id: str
    path: str
    file_role: str
    mime_type: str | None = None
    current_version_id: str | None = None
    content_hash: str | None = None
    sort_order: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismFileVersionPayload(BaseModel):
    id: str
    workspace_id: str
    file_id: str
    version_no: int
    mission_review_item_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismFileContentPayload(BaseModel):
    file: PrismFilePayload
    current_version: PrismFileVersionPayload | None = None


class PrismFileWritePayload(BaseModel):
    file: PrismFilePayload
    version: PrismFileVersionPayload | None = None
    changed: bool = False
    skipped_reason: str | None = None


class PrismProtectedScopePayload(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    document_id: str | None = None
    file_id: str | None = None
    file_path: str
    section_key: str = ""
    scope: str
    reason: str | None = None
    source: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismSurfacePayload(BaseModel):
    project: PrismProjectPayload
    documents: list[PrismDocumentPayload] = Field(default_factory=list)
    files: list[PrismFilePayload] = Field(default_factory=list)
