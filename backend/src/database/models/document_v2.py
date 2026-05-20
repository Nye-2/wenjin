"""Document v2 model for workspace documents."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class DocumentV2(Base, UUIDMixin, TimestampMixin):
    """A document in a workspace (v2 schema with versioning).

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        name: Document name
        kind: Document kind (draft/outline/figure/export/upload)
        mime_type: MIME type
        storage_path: Storage path
        size_bytes: File size in bytes
        parent_id: Self-FK for version chain
        version: Version number (starts at 1)
        metadata_json: Arbitrary metadata blob
        added_by: Who added this document
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "documents_v2"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents_v2.id"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<DocumentV2(id={self.id}, name={self.name!r}, v{self.version})>"
