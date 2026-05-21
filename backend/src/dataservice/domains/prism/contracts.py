"""Prism document domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PrismPrimaryProjectCommand(BaseModel):
    """Ensure one workspace primary Prism project."""

    workspace_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=255)
    adapter_kind: str = Field(default="latex", min_length=1, max_length=50)
    adapter_ref_id: str | None = Field(default=None, max_length=100)
    main_file: str = Field(default="main.tex", min_length=1, max_length=1024)
    settings_json: dict[str, Any] = Field(default_factory=dict)
    adapter_metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismFileCreateCommand(BaseModel):
    """Create one file node under a Prism document."""

    path: str = Field(min_length=1, max_length=1024)
    file_role: str = Field(default="generated", min_length=1, max_length=50)
    mime_type: str | None = Field(default=None, max_length=100)
    sort_order: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismFileVersionCreateCommand(BaseModel):
    """Append an immutable file version."""

    file_id: str = Field(min_length=1, max_length=36)
    review_item_id: str | None = Field(default=None, max_length=36)
    content_inline: str | None = None
    content_asset_id: str | None = Field(default=None, max_length=36)
    content_hash: str = Field(min_length=1, max_length=128)
    created_by: str = Field(default="system", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_content_pointer(self) -> PrismFileVersionCreateCommand:
        if bool(self.content_inline) == bool(self.content_asset_id):
            raise ValueError("Exactly one of content_inline or content_asset_id is required")
        return self


class PrismProtectedScopeUpsertCommand(BaseModel):
    """Create or update a protected Prism writing scope."""

    workspace_id: str = Field(min_length=1, max_length=36)
    project_id: str = Field(min_length=1, max_length=36)
    document_id: str | None = Field(default=None, max_length=36)
    file_id: str | None = Field(default=None, max_length=36)
    file_path: str = Field(min_length=1, max_length=1024)
    section_key: str = Field(default="", max_length=255)
    scope: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=1000)
    source: str = Field(min_length=1, max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrismProjectProjection(BaseModel):
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


class PrismDocumentProjection(BaseModel):
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


class PrismFileProjection(BaseModel):
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


class PrismFileVersionProjection(BaseModel):
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


class PrismProtectedScopeProjection(BaseModel):
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


class PrismSurfaceProjection(BaseModel):
    project: PrismProjectProjection
    documents: list[PrismDocumentProjection] = Field(default_factory=list)
    files: list[PrismFileProjection] = Field(default_factory=list)
