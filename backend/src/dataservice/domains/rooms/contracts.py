"""Workspace rooms domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionSetCommand(BaseModel):
    """Set one workspace decision and supersede the previous active value."""

    workspace_id: str = Field(min_length=1, max_length=36)
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1)
    extracted_by: str = Field(min_length=1, max_length=100)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_message_id: str | None = Field(default=None, max_length=36)
    source_review_batch_id: str | None = Field(default=None, max_length=36)
    source_review_item_id: str | None = Field(default=None, max_length=36)


class MemoryFactCreateCommand(BaseModel):
    """Create one workspace memory fact."""

    workspace_id: str = Field(min_length=1, max_length=36)
    category: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_review_batch_id: str | None = Field(default=None, max_length=36)
    source_review_item_id: str | None = Field(default=None, max_length=36)


class WorkspaceTaskCreateCommand(BaseModel):
    """Create one workspace task."""

    workspace_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: str = Field(default="pending", max_length=20)
    priority: int = 0
    related_execution_ids: list[str] = Field(default_factory=list)
    created_by: str = Field(default="system", min_length=1, max_length=100)
    source_review_batch_id: str | None = Field(default=None, max_length=36)
    source_review_item_id: str | None = Field(default=None, max_length=36)


class WorkspaceTaskUpdateCommand(BaseModel):
    """Update one workspace task."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = Field(default=None, max_length=20)
    priority: int | None = None
    related_execution_ids: list[str] | None = None


class DecisionProjection(BaseModel):
    """Canonical decision projection."""

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


class MemoryFactProjection(BaseModel):
    """Canonical memory fact projection."""

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


class WorkspaceTaskProjection(BaseModel):
    """Canonical workspace task projection."""

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


class RoomCandidateCommand(BaseModel):
    """One execution-produced candidate room write."""

    source_item_id: str | None = None
    target_kind: str = Field(pattern="^(decision|memory_fact|workspace_task)$")
    title: str
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)


class RoomCandidateApplyResult(BaseModel):
    """Result of staging and applying selected room candidates."""

    review_batch_id: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    item_results: list[dict[str, Any]] = Field(default_factory=list)
