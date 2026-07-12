"""Source library storage models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class SourceRecord(Base, UUIDMixin, TimestampMixin):
    """Canonical workspace source/reference record."""

    __tablename__ = "sources"
    __table_args__ = (
        Index(
            "uq_sources_ingest_mission_commit",
            "ingest_mission_commit_id",
            unique=True,
        ),
        Index("ix_sources_workspace_status", "workspace_id", "library_status"),
        Index("ix_sources_workspace_title", "workspace_id", "normalized_title"),
        Index("uq_sources_workspace_citation_key", "workspace_id", "citation_key", unique=True),
        Index(
            "uq_sources_workspace_doi_active",
            "workspace_id",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL AND is_deleted = false"),
            sqlite_where=text("doi IS NOT NULL AND is_deleted = 0"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingest_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", server_default="manual")
    ingest_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ingest_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    ingest_mission_commit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_commits.commit_id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    library_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate", server_default="candidate")
    evidence_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="metadata_only",
        server_default="metadata_only",
    )
    fulltext_status: Mapped[str] = mapped_column(String(32), nullable=False, default="none", server_default="none")
    citation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    bibtex_entry_type: Mapped[str] = mapped_column(String(50), nullable=False, default="article", server_default="article")
    bibtex_fields_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    read_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unread", server_default="unread")
    tags_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class SourceExternalIdRecord(Base, UUIDMixin, TimestampMixin):
    """Source-native external identifier."""

    __tablename__ = "source_external_ids"
    __table_args__ = (
        Index("uq_source_external_ids_workspace_provider_external", "workspace_id", "provider", "external_id", unique=True),
        Index("ix_source_external_ids_source", "source_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SourceAssetRecord(Base, UUIDMixin, TimestampMixin):
    """Association from a source to a workspace asset."""

    __tablename__ = "source_assets"
    __table_args__ = (
        Index("ix_source_assets_source_type", "source_id", "asset_type"),
        Index("ix_source_assets_workspace_status", "workspace_id", "preprocess_status"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"))
    workspace_asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspace_assets.id", ondelete="CASCADE"))
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    preprocess_status: Mapped[str] = mapped_column(String(32), nullable=False, default="skipped", server_default="skipped")
    manifest_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SourceOutlineNodeRecord(Base, UUIDMixin, TimestampMixin):
    """Outline/table-of-contents node for a source."""

    __tablename__ = "source_outline_nodes"
    __table_args__ = (
        Index("ix_source_outline_nodes_source_order", "source_id", "sort_order"),
        Index("ix_source_outline_nodes_parent", "parent_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"))
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    section_path: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")


class SourceTextUnitRecord(Base, UUIDMixin, TimestampMixin):
    """Indexed readable text unit for a source."""

    __tablename__ = "source_text_units"
    __table_args__ = (
        Index("ix_source_text_units_source_order", "source_id", "unit_index"),
        Index("ix_source_text_units_outline", "outline_node_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"))
    outline_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    unit_type: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SourceBibtexSnapshotRecord(Base, UUIDMixin, TimestampMixin):
    """Materialized BibTeX snapshot for a source set."""

    __tablename__ = "source_bibtex_snapshots"
    __table_args__ = (Index("ix_source_bibtex_snapshots_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    prism_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
