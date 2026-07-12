"""Provenance contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceLinkCreatePayload(BaseModel):
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
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None
    mission_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProvenanceLinkPayload(ProvenanceLinkCreatePayload):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
