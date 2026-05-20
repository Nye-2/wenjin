"""Provenance graph domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceLinkCreateCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    source_id: str | None = None
    source_anchor_id: str | None = None
    target_domain: str = Field(min_length=1, max_length=64)
    target_kind: str = Field(min_length=1, max_length=64)
    target_id: str | None = None
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    relation_kind: str = Field(min_length=1, max_length=64)
    citation_key: str | None = None
    claim_text: str | None = None
    generated_text: str | None = None
    review_item_id: str | None = None
    execution_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProvenanceLinkProjection(BaseModel):
    id: str
    workspace_id: str
    source_id: str | None = None
    source_anchor_id: str | None = None
    target_domain: str
    target_kind: str
    target_id: str | None = None
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    relation_kind: str
    citation_key: str | None = None
    claim_text: str | None = None
    generated_text: str | None = None
    review_item_id: str | None = None
    execution_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
