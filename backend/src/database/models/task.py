"""Task record model for persistent storage."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, generate_uuid


class TaskRecord(Base):
    """Persistent record of task execution.

    Attributes:
        id: UUID primary key
        user_id: ID of the user who owns this task
        task_type: Infrastructure task type (for example, 'reference_preprocess')
        status: Current status (pending, running, completed, failed, cancelled)
        priority: Task priority (1-10, higher = more important)
        payload: Task request payload as JSON
        result: Task result as JSON (null if not completed)
        error: Error message if task failed
        progress: Progress percentage (0-100)
        message: Human-readable progress message
        created_at: When the task was created
        started_at: When the task started processing
        completed_at: When the task finished (success or failure)
    """

    __tablename__ = "task_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Structured context fields — populated from payload at task creation
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Request
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Response
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_task_records_user_status", "user_id", "status"),
        Index("ix_task_records_user_created", "user_id", "created_at"),
        Index("ix_task_records_created_at", "created_at"),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_task_records_progress_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<TaskRecord {self.id[:8]} type={self.task_type} status={self.status}>"
