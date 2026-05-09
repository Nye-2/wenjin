"""Run history model for workspace execution history."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class RunHistory(Base, UUIDMixin):
    """A record of an execution run in a workspace.

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        execution_id: Unique execution identifier
        capability_id: Capability that was run
        title: Run title
        summary: Run summary
        status: Run status (completed/failed/cancelled)
        artifact_count: Number of artifacts produced
        duration_seconds: Duration in seconds
        token_usage: JSON token usage data
        created_at: Creation timestamp
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "run_history"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True,
    )
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<RunHistory(id={self.id}, title={self.title!r})>"
