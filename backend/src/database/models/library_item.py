"""Library item model for workspace reference library."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class LibraryItem(Base, UUIDMixin, TimestampMixin):
    """An item in a workspace's reference library.

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        item_type: Type of library item (e.g. article, book, misc)
        title: Item title
        authors: JSON list of author names
        year: Publication year
        venue: Publication venue
        doi: Digital Object Identifier
        url: URL to the item
        abstract: Item abstract
        full_text_path: Path to full text file
        metadata_json: Arbitrary metadata blob
        tags: JSON list of tags
        cited_in_documents: JSON list of document IDs citing this item
        added_by: Who added this item
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "library_items"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    cited_in_documents: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<LibraryItem(id={self.id}, title={self.title!r})>"
