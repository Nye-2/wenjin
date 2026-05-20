"""Rooms contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionSetPayload(BaseModel):
    workspace_id: str
    key: str
    value: str
    extracted_by: str
    confidence: float = 1.0
    source_message_id: str | None = None
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None


class MemoryFactCreatePayload(BaseModel):
    workspace_id: str
    category: str
    content: str
    confidence: float = 1.0
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None


class WorkspaceTaskCreatePayload(BaseModel):
    workspace_id: str
    title: str
    description: str | None = None
    status: str = "pending"
    priority: int = 0
    related_execution_ids: list[str] = Field(default_factory=list)
    created_by: str = "system"
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None


class WorkspaceTaskUpdatePayload(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    related_execution_ids: list[str] | None = None


class RoomCandidatePayload(BaseModel):
    source_item_id: str | None = None
    target_kind: str
    title: str
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)


class DecisionPayload(BaseModel):
    id: str
    workspace_id: str
    key: str
    value: str
    confidence: float
    source_message_id: str | None = None
    extracted_by: str
    superseded_by: str | None = None
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None


class MemoryFactPayload(BaseModel):
    id: str
    workspace_id: str
    category: str
    content: str
    confidence: float
    last_referenced_at: datetime | None = None
    reference_count: int = 0
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None


class WorkspaceTaskPayload(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None = None
    status: str
    priority: int
    related_execution_ids: list[str] = Field(default_factory=list)
    created_by: str
    source_review_batch_id: str | None = None
    source_review_item_id: str | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoomCandidateApplyPayload(BaseModel):
    review_batch_id: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    item_results: list[dict[str, Any]] = Field(default_factory=list)
