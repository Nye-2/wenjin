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
    review_item_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str = "system"


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
    review_item_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismSurfacePayload(BaseModel):
    project: PrismProjectPayload
    documents: list[PrismDocumentPayload] = Field(default_factory=list)
    files: list[PrismFilePayload] = Field(default_factory=list)
