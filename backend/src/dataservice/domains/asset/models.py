"""Workspace asset storage models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class WorkspaceAssetRecord(Base, UUIDMixin, TimestampMixin):
    """Canonical metadata for a managed workspace file/blob."""

    __tablename__ = "workspace_assets"
    __table_args__ = (
        Index("ix_workspace_assets_workspace_kind_created", "workspace_id", "asset_kind", "created_at"),
        Index("ix_workspace_assets_source", "source_kind", "source_id"),
        Index("ix_workspace_assets_content_hash", "content_hash"),
        Index("ix_workspace_assets_parent", "parent_asset_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(50), nullable=False, default="local", server_default="local")
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspace_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    source_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
