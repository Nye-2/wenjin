"""Review contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReviewItemCreatePayload(BaseModel):
    source_item_id: str | None = None
    item_kind: str
    target_domain: str
    target_kind: str
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    title: str
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class ReviewBatchCreatePayload(BaseModel):
    workspace_id: str
    execution_id: str | None = None
    source_type: str
    source_id: str | None = None
    review_kind: str
    title: str
    summary: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    items: list[ReviewItemCreatePayload] = Field(default_factory=list)


class ReviewItemDecisionPayload(BaseModel):
    status: str
    actor_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewItemTransitionPayload(BaseModel):
    status: str
    actor_id: str | None = None
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewItemPatchPayload(BaseModel):
    source_item_id: str | None = None
    item_kind: str | None = None
    target_domain: str | None = None
    target_kind: str | None = None
    target_ref_json: dict[str, Any] | None = None
    title: str | None = None
    summary: str | None = None
    payload_json: dict[str, Any] | None = None
    preview_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    provenance_json: dict[str, Any] | None = None
    sort_order: int | None = None


class ReviewItemDeletePayload(BaseModel):
    actor_id: str | None = None
    reason: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ReviewBatchPayload(BaseModel):
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


class ReviewItemPayload(BaseModel):
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


class ReviewBatchDetailPayload(BaseModel):
    batch: ReviewBatchPayload
    items: list[ReviewItemPayload] = Field(default_factory=list)
