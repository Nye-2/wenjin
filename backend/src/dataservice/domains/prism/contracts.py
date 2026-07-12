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


class PrismWorkspaceFileUpsertCommand(PrismFileCreateCommand):
    """Create or revive one workspace Prism file by path."""

    content_inline: str | None = None
    content_asset_id: str | None = Field(default=None, max_length=36)
    content_hash: str | None = Field(default=None, max_length=128)
    created_by: str = Field(default="system", min_length=1, max_length=100)
    mission_review_item_id: str | None = Field(default=None, max_length=36)
    mission_commit_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def validate_optional_content_pointer(self) -> PrismWorkspaceFileUpsertCommand:
        has_inline = self.content_inline is not None
        has_asset = self.content_asset_id is not None
        if has_inline and has_asset:
            raise ValueError("Only one of content_inline or content_asset_id may be provided")
        if (has_inline or has_asset) and not self.content_hash:
            raise ValueError("content_hash is required when initial content is provided")
        return self


class PrismFileVersionCreateCommand(BaseModel):
    """Append an immutable file version."""

    file_id: str = Field(min_length=1, max_length=36)
    mission_review_item_id: str | None = Field(default=None, max_length=36)
    mission_commit_id: str | None = Field(default=None, max_length=36)
    content_inline: str | None = None
    content_asset_id: str | None = Field(default=None, max_length=36)
    content_hash: str = Field(min_length=1, max_length=128)
    created_by: str = Field(default="system", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_content_pointer(self) -> PrismFileVersionCreateCommand:
        if (self.content_inline is not None) == (self.content_asset_id is not None):
            raise ValueError("Exactly one of content_inline or content_asset_id is required")
        return self


class PrismFileContentUpdateCommand(BaseModel):
    """Append a new version for a workspace Prism file if content changed."""

    content_inline: str | None = None
    content_asset_id: str | None = Field(default=None, max_length=36)
    content_hash: str = Field(min_length=1, max_length=128)
    created_by: str = Field(default="user", min_length=1, max_length=100)
    mission_review_item_id: str | None = Field(default=None, max_length=36)
    mission_commit_id: str | None = Field(default=None, max_length=36)
    expected_current_hash: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_pointer(self) -> PrismFileContentUpdateCommand:
        if bool(self.content_inline is not None) == bool(self.content_asset_id):
            raise ValueError("Exactly one of content_inline or content_asset_id is required")
        return self


class PrismFileRestoreCommand(BaseModel):
    """Restore one file to a previous version."""

    version_id: str = Field(min_length=1, max_length=36)
    expected_current_hash: str | None = Field(default=None, max_length=128)
    created_by: str = Field(default="system", min_length=1, max_length=100)


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
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrismFileContentProjection(BaseModel):
    file: PrismFileProjection
    current_version: PrismFileVersionProjection | None = None


class PrismFileWriteProjection(BaseModel):
    file: PrismFileProjection
    version: PrismFileVersionProjection | None = None
    changed: bool = False
    skipped_reason: str | None = None


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
