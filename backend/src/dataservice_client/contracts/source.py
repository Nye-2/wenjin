"""Source contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceCreatePayload(BaseModel):
    source_id: str | None = None
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
    verified_at: datetime | None = None
    library_status: str = "candidate"
    evidence_level: str = "metadata_only"
    fulltext_status: str = "none"
    citation_key: str
    bibtex_entry_type: str = "article"
    bibtex_fields_json: dict[str, Any] = Field(default_factory=dict)
    read_status: str = "unread"
    tags_json: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_deleted: bool = False


class SourceUpdatePayload(BaseModel):
    title: str | None = None
    normalized_title: str | None = None
    authors_json: list[Any] | None = None
    year: int | None = None
    venue: str | None = None
    publication_type: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    library_status: str | None = None
    citation_key: str | None = None
    bibtex_entry_type: str | None = None
    bibtex_fields_json: dict[str, Any] | None = None
    read_status: str | None = None
    tags_json: list[str] | None = None
    notes: str | None = None


class SourcePayload(SourceCreatePayload):
    id: str
    normalized_title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceBibliographyCreatePayload(BaseModel):
    workspace_id: str
    source_ids: list[str] = Field(default_factory=list)
    include_deleted: bool = False
    include_excluded: bool = False


class SourceBibliographyPayload(BaseModel):
    content: str | None = None
    count: int = 0
    source_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)


class SourceCitationUsageCreatePayload(BaseModel):
    workspace_id: str
    citation_keys: list[str] = Field(default_factory=list)
    execution_id: str | None = None
    task_id: str | None = None
    artifact_id: str | None = None
    latex_project_id: str | None = None
    target_domain: str = "prism"
    target_kind: str = "prism_file"
    target_id: str | None = None
    target_section: str | None = None
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    claim_text: str | None = None
    generated_text: str | None = None
    usage_type: str = "citation_only"
    accepted_status: str = "pending"
    mark_used_in_draft: bool = True


class SourceCitationUsagePayload(BaseModel):
    recorded: int
    source_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)
    provenance_link_ids: list[str] = Field(default_factory=list)
