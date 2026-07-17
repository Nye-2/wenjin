"""Contracts for hidden workspace memory documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.contracts.mission_write_authority import MissionWriteAuthority


class WorkspaceMemoryRewriteCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    content_markdown: str = Field(min_length=1)
    update_reason: str = Field(default="manual", min_length=1, max_length=100)
    updated_by: str = Field(default="system", min_length=1, max_length=100)
    source_mission_id: str | None = Field(default=None, max_length=36)
    source_mission_commit_id: str | None = Field(default=None, max_length=36)
    source_thread_id: str | None = Field(default=None, max_length=36)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceMemoryItemCommand(BaseModel):
    category: str = Field(default="context", min_length=1, max_length=50)
    content: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WorkspaceMemoryMergeCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    items: list[WorkspaceMemoryItemCommand] = Field(default_factory=list)
    update_reason: str = Field(default="mission_commit", min_length=1, max_length=100)
    updated_by: str = Field(default="system", min_length=1, max_length=100)
    source_mission_id: str | None = Field(default=None, max_length=36)
    source_mission_commit_id: str | None = Field(default=None, max_length=36)
    source_thread_id: str | None = Field(default=None, max_length=36)
    mission_write_authority: MissionWriteAuthority | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceMemoryDocumentProjection(BaseModel):
    id: str
    workspace_id: str
    content_markdown: str
    content_hash: str
    revision: int
    updated_by: str
    source_mission_id: str | None = None
    source_mission_commit_id: str | None = None
    source_thread_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceMemoryRevisionProjection(BaseModel):
    id: str
    workspace_id: str
    document_id: str
    revision: int
    content_markdown: str
    content_hash: str
    update_reason: str
    source_mission_id: str | None = None
    source_mission_commit_id: str | None = None
    source_thread_id: str | None = None
    created_by: str
    created_at: datetime | None = None


class WorkspaceMemoryWriteProjection(BaseModel):
    document: WorkspaceMemoryDocumentProjection
    revision: WorkspaceMemoryRevisionProjection | None = None
    changed: bool = False
    skipped_reason: str | None = None
