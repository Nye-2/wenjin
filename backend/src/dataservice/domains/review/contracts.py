"""Review batch domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

BATCH_STATUSES = {"pending", "partially_applied", "applied", "rejected", "failed"}
ITEM_STATUSES = {"pending", "accepted", "rejected", "applied", "reverted", "failed"}


class ReviewItemCreateCommand(BaseModel):
    """Create one staged review item."""

    source_item_id: str | None = Field(default=None, max_length=255)
    item_kind: str = Field(min_length=1, max_length=64)
    target_domain: str = Field(min_length=1, max_length=64)
    target_kind: str = Field(min_length=1, max_length=64)
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class ReviewBatchCreateCommand(BaseModel):
    """Create one user-reviewable batch."""

    workspace_id: str = Field(min_length=1, max_length=36)
    execution_id: str | None = Field(default=None, max_length=36)
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str | None = Field(default=None, max_length=255)
    review_kind: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    items: list[ReviewItemCreateCommand] = Field(default_factory=list)


class ReviewItemDecisionCommand(BaseModel):
    """Set a user decision on a review item."""

    status: str = Field(pattern="^(accepted|rejected|pending)$")
    actor_id: str | None = Field(default=None, max_length=36)
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewItemTransitionCommand(BaseModel):
    """Apply a terminal item transition."""

    status: str = Field(pattern="^(applied|reverted|failed)$")
    actor_id: str | None = Field(default=None, max_length=36)
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewItemPatchCommand(BaseModel):
    """Patch non-transition review item metadata and payload."""

    source_item_id: str | None = Field(default=None, max_length=255)
    item_kind: str | None = Field(default=None, min_length=1, max_length=64)
    target_domain: str | None = Field(default=None, min_length=1, max_length=64)
    target_kind: str | None = Field(default=None, min_length=1, max_length=64)
    target_ref_json: dict[str, Any] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    payload_json: dict[str, Any] | None = None
    preview_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    provenance_json: dict[str, Any] | None = None
    sort_order: int | None = None


class ReviewItemDeleteCommand(BaseModel):
    """Delete a review item that should no longer be user-reviewable."""

    actor_id: str | None = Field(default=None, max_length=36)
    reason: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewBatchProjection(BaseModel):
    """Canonical review batch projection."""

    id: str
    workspace_id: str
    execution_id: str | None = None
    source_type: str
    source_id: str | None = None
    review_kind: str
    status: str
    title: str
    summary: str | None = None
    schema_version: str
    item_count: int
    accepted_count: int
    rejected_count: int
    applied_count: int
    failed_count: int
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewItemProjection(BaseModel):
    """Canonical review item projection."""

    id: str
    batch_id: str
    workspace_id: str
    source_item_id: str | None = None
    item_kind: str
    target_domain: str
    target_kind: str
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    title: str
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    applied_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewActionLogProjection(BaseModel):
    """Canonical review action log projection."""

    id: str
    batch_id: str
    item_id: str | None = None
    workspace_id: str
    action: str
    actor_id: str | None = None
    status_from: str | None = None
    status_to: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewBatchDetailProjection(BaseModel):
    """Batch projection with ordered items."""

    batch: ReviewBatchProjection
    items: list[ReviewItemProjection] = Field(default_factory=list)
