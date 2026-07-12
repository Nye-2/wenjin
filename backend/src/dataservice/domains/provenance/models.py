"""Provenance graph storage models owned by DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class SourceAnchorRecord(Base, UUIDMixin, TimestampMixin):
    """Stable anchor inside a source or source-derived asset."""

    __tablename__ = "source_anchors"
    __table_args__ = (
        Index("ix_source_anchors_source", "source_id"),
        Index("ix_source_anchors_workspace_kind", "workspace_id", "anchor_kind"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True)
    source_text_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    anchor_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    anchor_key: Mapped[str] = mapped_column(String(255), nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class ProvenanceLinkRecord(Base, UUIDMixin, TimestampMixin):
    """Link from a source anchor to a target entity."""

    __tablename__ = "provenance_links"
    __table_args__ = (
        Index("ix_provenance_links_workspace_created", "workspace_id", "created_at"),
        Index("ix_provenance_links_source", "source_id"),
        Index("ix_provenance_links_target", "target_domain", "target_kind", "target_id"),
        Index("ix_provenance_links_mission_review_item", "mission_review_item_id"),
        Index("ix_provenance_links_mission_commit", "mission_commit_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    source_anchor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_anchors.id", ondelete="SET NULL"), nullable=True)
    target_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_ref_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    relation_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    citation_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission_review_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_review_items.review_item_id", ondelete="SET NULL"),
        nullable=True,
    )
    mission_commit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_commits.commit_id", ondelete="SET NULL"),
        nullable=True,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
