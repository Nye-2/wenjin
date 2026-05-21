"""Workspace-scoped reference library models."""

from __future__ import annotations

import enum


class ReferenceSourceType(enum.StrEnum):
    """How a reference entered a workspace library."""

    UPLOAD = "upload"
    SEMANTIC_SCHOLAR = "semantic_scholar"
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
