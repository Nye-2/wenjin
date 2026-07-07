"""Source contracts returned by DataService client methods."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReferenceSourceType(enum.StrEnum):
    """How a reference entered a workspace library."""

    UPLOAD = "upload"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    WEB_SEARCH = "web_search"
    CURATED_ACADEMIC = "curated_academic"
    DEEP_SEARCH = "deep_search"
    MANUAL = "manual"
    BIBTEX = "bibtex"


class ReferenceLibraryStatus(enum.StrEnum):
    """User-facing curation state for a workspace reference."""

    CANDIDATE = "candidate"
    INCLUDED = "included"
    CORE = "core"
    EXCLUDED = "excluded"
    USED_IN_DRAFT = "used_in_draft"


class ReferenceEvidenceLevel(enum.StrEnum):
    """Trust and evidence level of a reference record."""

    METADATA_ONLY = "metadata_only"
    EXTERNAL_VERIFIED = "external_verified"
    UPLOADED_FULLTEXT = "uploaded_fulltext"
    INDEXED_FULLTEXT = "indexed_fulltext"


class ReferenceFulltextStatus(enum.StrEnum):
    """Full-text availability/indexing status."""

    NONE = "none"
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    INDEXED = "indexed"
    FAILED = "failed"


class ReferenceReadStatus(enum.StrEnum):
    """Human reading status for a reference."""

    UNREAD = "unread"
    READING = "reading"
    READ = "read"
    SKIMMED = "skimmed"


class ReferenceAssetType(enum.StrEnum):
    """Persisted file asset types attached to a reference."""

    PDF = "pdf"
    MARKDOWN = "markdown"
    MANIFEST = "manifest"
    IMAGE = "image"
    SUPPLEMENTARY = "supplementary"


class ReferencePreprocessStatus(enum.StrEnum):
    """Preprocessing lifecycle for a reference asset."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReferenceTextUnitType(enum.StrEnum):
    """Granularity of indexed readable text."""

    SECTION = "section"
    PAGE = "page"
    PARAGRAPH = "paragraph"
    CHUNK = "chunk"
    ABSTRACT = "abstract"


class ReferenceUsageType(enum.StrEnum):
    """How a reference was used during writing."""

    BACKGROUND = "background"
    COMPARISON = "comparison"
    METHOD_SUPPORT = "method_support"
    DATASET = "dataset"
    LIMITATION = "limitation"
    RESULT_DISCUSSION = "result_discussion"
    CITATION_ONLY = "citation_only"


class ReferenceAcceptedStatus(enum.StrEnum):
    """Human acceptance state for a recorded reference use."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class ReferenceBibtexScope(enum.StrEnum):
    """Scope used to project refs.bib."""

    USED_ONLY = "used_only"
    CORE = "core"
    INCLUDED_AND_CORE = "included_and_core"
    ALL_NON_EXCLUDED = "all_non_excluded"


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
    evidence_level: str | None = None
    fulltext_status: str | None = None
    library_status: str | None = None
    citation_key: str | None = None
    bibtex_entry_type: str | None = None
    bibtex_fields_json: dict[str, Any] | None = None
    read_status: str | None = None
    tags_json: list[str] | None = None
    notes: str | None = None


class SourceExternalIdCreatePayload(BaseModel):
    provider: str
    external_id: str
    url: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SourceAssetUpdatePayload(BaseModel):
    preprocess_status: str | None = None
    manifest_asset_id: str | None = None
    metadata_json: dict[str, Any] | None = None


class SourceAssetLinkPayload(BaseModel):
    workspace_id: str
    source_id: str
    workspace_asset_id: str
    asset_type: str
    source_asset_id: str | None = None
    preprocess_status: str = "skipped"
    manifest_asset_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SourceImportPayload(SourceCreatePayload):
    external_ids: list[SourceExternalIdCreatePayload] = Field(default_factory=list)
    dedupe_by_title: bool = True


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


class SourceImportResultPayload(BaseModel):
    source: SourcePayload
    created: bool
    external_ids: list[dict[str, Any]] = Field(default_factory=list)


class SourceBibliographyPayload(BaseModel):
    content: str | None = None
    count: int = 0
    source_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)


class SourceBibliographySnapshotCreatePayload(BaseModel):
    workspace_id: str
    prism_project_id: str | None = None
    scope: str = "included_and_core"
    content: str
    reference_count: int = 0
    checksum: str


class SourceBibliographySnapshotPayload(BaseModel):
    id: str
    workspace_id: str
    prism_project_id: str | None = None
    scope: str
    content: str
    reference_count: int
    checksum: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceEvidencePackCreatePayload(BaseModel):
    workspace_id: str
    query: str | None = None
    source_ids: list[str] | None = None
    max_units: int = 8


class SourceEvidencePackPayload(BaseModel):
    workspace_id: str
    query: str | None = None
    library_outline: list[dict[str, Any]] = Field(default_factory=list)
    selected_units: list[dict[str, Any]] = Field(default_factory=list)
    policy: str = "outline_first_no_vector_rag"


class SourceIndexReplacePayload(BaseModel):
    workspace_id: str
    source_id: str
    outline_nodes: list[dict[str, Any]] = Field(default_factory=list)
    text_units: list[dict[str, Any]] = Field(default_factory=list)


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
