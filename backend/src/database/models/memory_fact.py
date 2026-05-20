"""Memory fact model for workspace memory."""

from datetime import datetime

from sqlalchemy import REAL, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class MemoryFact(Base, UUIDMixin):
    """A memory fact stored in a workspace.

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        category: Fact category (writing_style/domain_term/user_habit/context)
        content: Fact content text
        confidence: Confidence score (0.0-1.0)
        last_referenced_at: Last time this fact was referenced
        reference_count: Number of times referenced
        created_at: Creation timestamp
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "memory_facts"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False, default=1.0)
    last_referenced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reference_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    source_review_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("review_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_review_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("review_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<MemoryFact(id={self.id}, category={self.category!r})>"
