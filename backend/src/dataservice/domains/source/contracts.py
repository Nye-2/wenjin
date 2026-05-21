"""Source library domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceCreateCommand(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    workspace_id: str = Field(min_length=1, max_length=36)
    source_kind: str = Field(default="paper", min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=1000)
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


class SourceUpdateCommand(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
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


class SourceProjection(BaseModel):
    id: str
    workspace_id: str
    source_kind: str
    title: str
    normalized_title: str
    authors_json: list[Any] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    publication_type: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    ingest_kind: str
    ingest_label: str | None = None
    ingest_execution_id: str | None = None
    verified_at: datetime | None = None
    library_status: str
    evidence_level: str
    fulltext_status: str
    citation_key: str
    bibtex_entry_type: str
    bibtex_fields_json: dict[str, Any] = Field(default_factory=dict)
    read_status: str
    tags_json: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceBibliographyCreateCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    source_ids: list[str] = Field(default_factory=list)
    include_deleted: bool = False
    include_excluded: bool = False


class SourceBibliographyProjection(BaseModel):
    content: str | None = None
    count: int = 0
    source_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)


class SourceCitationUsageCreateCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    citation_keys: list[str] = Field(default_factory=list)
    execution_id: str | None = None
    task_id: str | None = None
    artifact_id: str | None = None
    latex_project_id: str | None = None
    target_domain: str = Field(default="prism", min_length=1, max_length=64)
    target_kind: str = Field(default="prism_file", min_length=1, max_length=64)
    target_id: str | None = None
    target_section: str | None = None
    target_ref_json: dict[str, Any] = Field(default_factory=dict)
    claim_text: str | None = None
    generated_text: str | None = None
    usage_type: str = Field(default="citation_only", min_length=1, max_length=64)
    accepted_status: str = Field(default="pending", min_length=1, max_length=64)
    mark_used_in_draft: bool = True


class SourceCitationUsageProjection(BaseModel):
    recorded: int
    source_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)
    provenance_link_ids: list[str] = Field(default_factory=list)
