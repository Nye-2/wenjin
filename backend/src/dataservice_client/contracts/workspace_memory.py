"""Workspace memory contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.contracts.mission_write_authority import MissionWriteAuthority


class WorkspaceMemoryRewritePayload(BaseModel):
    workspace_id: str
    content_markdown: str
    update_reason: str = "manual"
    updated_by: str = "system"
    source_mission_id: str | None = None
    source_mission_commit_id: str | None = None
    source_thread_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceMemoryItemPayload(BaseModel):
    category: str = "context"
    content: str
    confidence: float = 1.0


class WorkspaceMemoryMergePayload(BaseModel):
    workspace_id: str
    items: list[WorkspaceMemoryItemPayload] = Field(default_factory=list)
    update_reason: str = "mission_commit"
    updated_by: str = "system"
    source_mission_id: str | None = None
    source_mission_commit_id: str | None = None
    source_thread_id: str | None = None
    mission_write_authority: MissionWriteAuthority | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceMemoryDocumentPayload(BaseModel):
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


class WorkspaceMemoryRevisionPayload(BaseModel):
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


class WorkspaceMemoryWritePayload(BaseModel):
    document: WorkspaceMemoryDocumentPayload
    revision: WorkspaceMemoryRevisionPayload | None = None
    changed: bool = False
    skipped_reason: str | None = None
