"""Canonical workspace Prism integration models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class PrismReviewItem(Base, UUIDMixin, TimestampMixin):
    """DB-backed review state for Prism and workspace result review."""

    __tablename__ = "prism_review_items"
    __table_args__ = (
        UniqueConstraint(
            "latex_project_id",
            "logical_key",
            name="uq_prism_review_items_project_logical_key",
        ),
        Index("ix_prism_review_items_workspace_status", "workspace_id", "status"),
        Index("ix_prism_review_items_project_status", "latex_project_id", "status"),
        Index("ix_prism_review_items_source_execution", "source_execution_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    latex_project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("latex_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    logical_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_room: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    preview_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PrismSourceLink(Base, UUIDMixin, TimestampMixin):
    """Provenance link between manuscript changes and workspace sources."""

    __tablename__ = "prism_source_links"
    __table_args__ = (
        Index("ix_prism_source_links_workspace", "workspace_id"),
        Index("ix_prism_source_links_review_item", "review_item_id"),
        Index("ix_prism_source_links_source", "source_type", "source_id"),
        Index("ix_prism_source_links_project_file", "latex_project_id", "file_path"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    latex_project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("latex_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("prism_review_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    section_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
    )
    quote: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    citation_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage: Mapped[str] = mapped_column(String(64), nullable=False)


class PrismProtectedSection(Base, UUIDMixin, TimestampMixin):
    """Section or file scope that agent writing must not overwrite directly."""

    __tablename__ = "prism_protected_sections"
    __table_args__ = (
        UniqueConstraint(
            "latex_project_id",
            "file_path",
            "section_key",
            "scope",
            name="uq_prism_protected_sections_scope",
        ),
        Index("ix_prism_protected_sections_workspace", "workspace_id"),
        Index("ix_prism_protected_sections_project", "latex_project_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    latex_project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("latex_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    section_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
