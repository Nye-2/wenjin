"""Rooms contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.contracts.mission_write_authority import MissionWriteAuthority


class DecisionSetPayload(BaseModel):
    workspace_id: str
    key: str
    value: str
    extracted_by: str
    confidence: float = 1.0
    source_message_id: str | None = None
    source_mission_id: str | None = None
    source_mission_item_seq: int | None = None
    source_mission_commit_id: str | None = None
    mission_write_authority: MissionWriteAuthority | None = None


class WorkspaceTaskCreatePayload(BaseModel):
    workspace_id: str
    title: str
    description: str | None = None
    status: str = "pending"
    priority: int = 0
    related_mission_ids: list[str] = Field(default_factory=list)
    created_by: str = "system"
    source_mission_id: str | None = None
    source_mission_item_seq: int | None = None
    source_mission_commit_id: str | None = None
    mission_write_authority: MissionWriteAuthority | None = None


class WorkspaceTaskUpdatePayload(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    related_mission_ids: list[str] | None = None


class DecisionPayload(BaseModel):
    id: str
    workspace_id: str
    key: str
    value: str
    confidence: float
    source_message_id: str | None = None
    extracted_by: str
    superseded_by: str | None = None
    source_mission_id: str | None = None
    source_mission_item_seq: int | None = None
    source_mission_commit_id: str | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None


class WorkspaceTaskPayload(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None = None
    status: str
    priority: int
    related_mission_ids: list[str] = Field(default_factory=list)
    created_by: str
    source_mission_id: str | None = None
    source_mission_item_seq: int | None = None
    source_mission_commit_id: str | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
