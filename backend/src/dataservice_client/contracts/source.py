"""Source contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceCreatePayload(BaseModel):
    workspace_id: str
    source_kind: str = "paper"
    title: str
    normalized_title: str | None = None
    authors_json: list[Any] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    publication_type: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    ingest_kind: str = "manual"
    ingest_label: str | None = None
    ingest_execution_id: str | None = None
    library_status: str = "candidate"
    evidence_level: str = "metadata_only"
    fulltext_status: str = "none"
    citation_key: str
    bibtex_entry_type: str = "article"
    bibtex_fields_json: dict[str, Any] = Field(default_factory=dict)
    read_status: str = "unread"
    tags_json: list[str] = Field(default_factory=list)
    notes: str | None = None


class SourcePayload(SourceCreatePayload):
    id: str
    normalized_title: str
    verified_at: datetime | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
