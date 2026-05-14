"""Workspace-scoped reference library models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .workspace import Workspace


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


def _enum(enum_cls: type[enum.StrEnum]) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
    )


class WorkspaceReference(Base, UUIDMixin, TimestampMixin):
    """Canonical workspace-scoped literature/reference record."""

    __tablename__ = "workspace_references"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "citation_key",
            name="uq_workspace_references_workspace_citation_key",
        ),
        Index("ix_workspace_references_workspace_status", "workspace_id", "library_status"),
        Index("ix_workspace_references_workspace_created", "workspace_id", "created_at"),
        Index("ix_workspace_references_workspace_title", "workspace_id", "normalized_title"),
        Index(
            "uq_workspace_references_workspace_doi_active",
            "workspace_id",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL AND is_deleted = false"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source_type: Mapped[ReferenceSourceType] = mapped_column(
        _enum(ReferenceSourceType),
        nullable=False,
    )
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    library_status: Mapped[ReferenceLibraryStatus] = mapped_column(
        _enum(ReferenceLibraryStatus),
        nullable=False,
        default=ReferenceLibraryStatus.CANDIDATE,
        server_default=ReferenceLibraryStatus.CANDIDATE.value,
    )
    evidence_level: Mapped[ReferenceEvidenceLevel] = mapped_column(
        _enum(ReferenceEvidenceLevel),
        nullable=False,
        default=ReferenceEvidenceLevel.METADATA_ONLY,
        server_default=ReferenceEvidenceLevel.METADATA_ONLY.value,
    )
    fulltext_status: Mapped[ReferenceFulltextStatus] = mapped_column(
        _enum(ReferenceFulltextStatus),
        nullable=False,
        default=ReferenceFulltextStatus.NONE,
        server_default=ReferenceFulltextStatus.NONE.value,
    )

    citation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    bibtex_entry_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="article",
        server_default="article",
    )
    bibtex_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    read_status: Mapped[ReferenceReadStatus] = mapped_column(
        _enum(ReferenceReadStatus),
        nullable=False,
        default=ReferenceReadStatus.UNREAD,
        server_default=ReferenceReadStatus.UNREAD.value,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="references")
    external_ids: Mapped[list[ReferenceExternalId]] = relationship(
        "ReferenceExternalId",
        back_populates="reference",
        cascade="all, delete-orphan",
    )
    assets: Mapped[list[ReferenceAsset]] = relationship(
        "ReferenceAsset",
        back_populates="reference",
        cascade="all, delete-orphan",
    )
    outline_nodes: Mapped[list[ReferenceOutlineNode]] = relationship(
        "ReferenceOutlineNode",
        back_populates="reference",
        cascade="all, delete-orphan",
    )
    text_units: Mapped[list[ReferenceTextUnit]] = relationship(
        "ReferenceTextUnit",
        back_populates="reference",
        cascade="all, delete-orphan",
    )


class ReferenceExternalId(Base, UUIDMixin, TimestampMixin):
    """Source-native identifier attached to a workspace reference."""

    __tablename__ = "reference_external_ids"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source",
            "external_id",
            name="uq_reference_external_ids_workspace_source_external",
        ),
        Index("ix_reference_external_ids_reference", "reference_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    reference: Mapped[WorkspaceReference] = relationship(
        "WorkspaceReference",
        back_populates="external_ids",
    )


class ReferenceAsset(Base, UUIDMixin, TimestampMixin):
    """Persisted full-text or supplemental asset for a reference."""

    __tablename__ = "reference_assets"
    __table_args__ = (
        Index("ix_reference_assets_reference_type", "reference_id", "asset_type"),
        Index("ix_reference_assets_workspace_status", "workspace_id", "preprocess_status"),
        Index("ix_reference_assets_source_asset", "source_asset_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_assets.id", ondelete="CASCADE"),
        nullable=True,
    )
    asset_type: Mapped[ReferenceAssetType] = mapped_column(
        _enum(ReferenceAssetType),
        nullable=False,
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    virtual_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preprocess_status: Mapped[ReferencePreprocessStatus] = mapped_column(
        _enum(ReferencePreprocessStatus),
        nullable=False,
        default=ReferencePreprocessStatus.SKIPPED,
        server_default=ReferencePreprocessStatus.SKIPPED.value,
    )
    preprocess_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    preprocess_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_paths: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    reference: Mapped[WorkspaceReference] = relationship(
        "WorkspaceReference",
        back_populates="assets",
    )


class ReferenceOutlineNode(Base, UUIDMixin, TimestampMixin):
    """Outline/table-of-contents node used by the page-index workflow."""

    __tablename__ = "reference_outline_nodes"
    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "section_path",
            name="uq_reference_outline_nodes_reference_section_path",
        ),
        Index("ix_reference_outline_nodes_workspace_reference", "workspace_id", "reference_id"),
        Index("ix_reference_outline_nodes_parent", "parent_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_outline_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    section_path: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(1000), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    reference: Mapped[WorkspaceReference] = relationship(
        "WorkspaceReference",
        back_populates="outline_nodes",
    )
    parent: Mapped[ReferenceOutlineNode | None] = relationship(
        "ReferenceOutlineNode",
        remote_side="ReferenceOutlineNode.id",
    )


class ReferenceTextUnit(Base, UUIDMixin, TimestampMixin):
    """Readable text unit selected after outline/page navigation."""

    __tablename__ = "reference_text_units"
    __table_args__ = (
        Index("ix_reference_text_units_workspace_reference", "workspace_id", "reference_id"),
        Index("ix_reference_text_units_outline", "outline_node_id"),
        Index(
            "ix_reference_text_units_search_fts",
            text("to_tsvector('simple', search_text)"),
            postgresql_using="gin",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    outline_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_outline_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    unit_type: Mapped[ReferenceTextUnitType] = mapped_column(
        _enum(ReferenceTextUnitType),
        nullable=False,
    )
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    unit_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    reference: Mapped[WorkspaceReference] = relationship(
        "WorkspaceReference",
        back_populates="text_units",
    )
    outline_node: Mapped[ReferenceOutlineNode | None] = relationship("ReferenceOutlineNode")
    asset: Mapped[ReferenceAsset | None] = relationship("ReferenceAsset")


class ReferenceUsageEvent(Base, UUIDMixin, TimestampMixin):
    """Audit/event row recording how reference evidence supported writing."""

    __tablename__ = "reference_usage_events"
    __table_args__ = (
        Index("ix_reference_usage_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_reference_usage_events_reference", "reference_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    outline_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_outline_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    text_unit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_text_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latex_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage_type: Mapped[ReferenceUsageType] = mapped_column(
        _enum(ReferenceUsageType),
        nullable=False,
        default=ReferenceUsageType.BACKGROUND,
        server_default=ReferenceUsageType.BACKGROUND.value,
    )
    accepted_status: Mapped[ReferenceAcceptedStatus] = mapped_column(
        _enum(ReferenceAcceptedStatus),
        nullable=False,
        default=ReferenceAcceptedStatus.PENDING,
        server_default=ReferenceAcceptedStatus.PENDING.value,
    )


class ReferenceBibtexSnapshot(Base, UUIDMixin, TimestampMixin):
    """Materialized refs.bib projection snapshot."""

    __tablename__ = "reference_bibtex_snapshots"
    __table_args__ = (
        Index("ix_reference_bibtex_snapshots_workspace_created", "workspace_id", "created_at"),
        Index("ix_reference_bibtex_snapshots_project_scope", "latex_project_id", "scope"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    latex_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scope: Mapped[ReferenceBibtexScope] = mapped_column(
        _enum(ReferenceBibtexScope),
        nullable=False,
        default=ReferenceBibtexScope.INCLUDED_AND_CORE,
        server_default=ReferenceBibtexScope.INCLUDED_AND_CORE.value,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
