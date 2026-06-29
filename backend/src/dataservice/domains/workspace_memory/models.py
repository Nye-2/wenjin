"""Hidden workspace memory document models."""

from __future__ import annotations

from typing import Any

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class WorkspaceMemoryDocumentRecord(Base, UUIDMixin, TimestampMixin):
    """Current backend-maintained Markdown memory for one workspace."""

    __tablename__ = "workspace_memory_documents"
    __table_args__ = (
        Index("uq_workspace_memory_documents_workspace", "workspace_id", unique=True),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    source_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class WorkspaceMemoryRevisionRecord(Base, UUIDMixin):
    """Immutable revision snapshot for the workspace memory document."""

    __tablename__ = "workspace_memory_revisions"
    __table_args__ = (
        Index("uq_workspace_memory_revisions_document_revision", "document_id", "revision", unique=True),
        Index("ix_workspace_memory_revisions_workspace_revision", "workspace_id", "revision"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_memory_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    update_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    source_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
