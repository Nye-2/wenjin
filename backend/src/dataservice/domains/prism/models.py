"""Prism document storage models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class PrismProjectRecord(Base, UUIDMixin, TimestampMixin):
    """Workspace-owned Prism surface container."""

    __tablename__ = "prism_projects"
    __table_args__ = (
        Index(
            "uq_prism_projects_workspace_primary_active",
            "workspace_id",
            "role",
            unique=True,
            postgresql_where=text("role = 'primary_manuscript' AND status = 'active' AND trashed_at IS NULL"),
            sqlite_where=text("role = 'primary_manuscript' AND status = 'active' AND trashed_at IS NULL"),
        ),
        Index("ix_prism_projects_workspace_status", "workspace_id", "status"),
        Index("ix_prism_projects_adapter_ref", "adapter_kind", "adapter_ref_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="latex", server_default="latex")
    adapter_ref_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    adapter_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrismDocumentRecord(Base, UUIDMixin, TimestampMixin):
    """Logical document inside a Prism project."""

    __tablename__ = "prism_documents"
    __table_args__ = (
        Index("ix_prism_documents_workspace_status", "workspace_id", "status"),
        Index("ix_prism_documents_project_kind", "project_id", "document_kind"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prism_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="latex", server_default="latex")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    root_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class PrismFileRecord(Base, UUIDMixin, TimestampMixin):
    """Editable file node in a Prism document."""

    __tablename__ = "prism_files"
    __table_args__ = (
        Index("uq_prism_files_document_path", "document_id", "path", unique=True),
        Index("ix_prism_files_workspace", "workspace_id"),
        Index("ix_prism_files_document_order", "document_id", "sort_order"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prism_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_role: Mapped[str] = mapped_column(String(50), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrismFileVersionRecord(Base, UUIDMixin, TimestampMixin):
    """Immutable file content version."""

    __tablename__ = "prism_file_versions"
    __table_args__ = (
        Index("uq_prism_file_versions_file_version", "file_id", "version_no", unique=True),
        Index("ix_prism_file_versions_workspace_created", "workspace_id", "created_at"),
        Index("ix_prism_file_versions_review_item", "review_item_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prism_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    review_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_inline: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)


class PrismRenderRecord(Base, UUIDMixin, TimestampMixin):
    """Render/compile output for a Prism document."""

    __tablename__ = "prism_renders"
    __table_args__ = (
        Index("ix_prism_renders_document_created", "document_id", "created_at"),
        Index("ix_prism_renders_workspace_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prism_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    render_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    engine: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    output_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    log_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrismProtectedScopeRecord(Base, UUIDMixin, TimestampMixin):
    """Scope that agent writing must not overwrite directly."""

    __tablename__ = "prism_protected_scopes"
    __table_args__ = (
        Index("uq_prism_protected_scopes_scope", "project_id", "file_path", "section_key", "scope", unique=True),
        Index("ix_prism_protected_scopes_workspace", "workspace_id"),
        Index("ix_prism_protected_scopes_project", "project_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prism_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    section_key: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
