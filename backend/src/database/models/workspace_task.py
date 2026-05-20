"""Workspace task model for workspace-level tasks."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class WorkspaceTask(Base, UUIDMixin, TimestampMixin):
    """A task tracked at the workspace level.

    Attributes:
        id: UUID primary key
        workspace_id: FK to workspaces.id (cascade delete)
        title: Task title
        description: Optional task description
        status: Task status (pending/in_progress/done)
        priority: Priority (higher = more important)
        related_execution_ids: JSON list of related execution IDs
        created_by: Who created this task
        completed_at: When the task was completed
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "workspace_tasks"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    related_execution_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<WorkspaceTask(id={self.id}, title={self.title!r}, status={self.status})>"
