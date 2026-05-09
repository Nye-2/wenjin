"""Persistent records for subagent execution lifecycle."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base

TASK_METADATA_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class SubagentTaskRecord(Base):
    """Durable projection of subagent lifecycle state."""

    __tablename__ = "subagent_task_records"
    __table_args__ = (
        Index("ix_subagent_task_records_workspace_updated", "workspace_id", "updated_at"),
        Index("ix_subagent_task_records_thread_created", "thread_id", "created_at"),
        Index("ix_subagent_task_records_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    execution_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("execution_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    subagent_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_metadata: Mapped[dict[str, Any]] = mapped_column(
        TASK_METADATA_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    criticality: Mapped[str] = mapped_column(String(8), default="low", nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspace_run.id"), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("executions.id"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SubagentTaskRecord(id={self.id}, thread_id={self.thread_id}, "
            f"status={self.status})>"
        )
