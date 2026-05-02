"""Execution session model for converged thread->feature runtime state."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, generate_uuid


class ExecutionSessionStatus(StrEnum):
    """Canonical execution session lifecycle statuses."""

    LAUNCHING = "launching"
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_USER_INPUT = "awaiting_user_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ADVISORY = "advisory"


class ExecutionSessionRecord(Base):
    """Persistent aggregate for a launched workspace feature execution."""

    __tablename__ = "execution_sessions"
    __table_args__ = (
        Index("ix_execution_sessions_workspace_updated", "workspace_id", "updated_at"),
        Index(
            "ix_execution_sessions_user_workspace_updated",
            "user_id",
            "workspace_id",
            "updated_at",
        ),
        Index("ix_execution_sessions_thread_created", "thread_id", "created_at"),
        Index("ix_execution_sessions_primary_task_id", "primary_task_id"),
        Index("ix_execution_sessions_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    workspace_type: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    launch_source: Mapped[str] = mapped_column(String(20), nullable=False, default="thread")
    launch_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="launching")

    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    task_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    primary_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    runtime_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    next_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    advisory_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ExecutionSessionRecord(id={self.id}, workspace_id={self.workspace_id}, "
            f"feature_id={self.feature_id}, status={self.status})>"
        )
