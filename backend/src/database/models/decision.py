"""Decision model for workspace decisions."""

from datetime import datetime

from sqlalchemy import REAL, BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class Decision(Base, UUIDMixin):
    """A tracked decision in a workspace.

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        key: Decision key (e.g. citation_style)
        value: Decision value
        confidence: Confidence score (0.0-1.0)
        source_message_id: Optional source message ID
        extracted_by: Actor that extracted this decision
        superseded_by: Self-FK to the decision that supersedes this one
        created_at: Creation timestamp
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "decisions"
    __table_args__ = (
        Index("uq_decisions_mission_commit", "source_mission_commit_id", unique=True),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False, default=1.0)
    source_message_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    extracted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("decisions.id"),
        nullable=True,
    )
    source_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_mission_item_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_mission_commit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_commits.commit_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Decision(id={self.id}, key={self.key!r}, value={self.value!r})>"
