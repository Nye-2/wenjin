"""Execution record model for unified execution tracking."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, generate_uuid


class ExecutionRecord(Base):
    """Unified execution record — SSOT for all execution types.

    Replaces: TaskRecord, ExecutionSessionRecord, WorkspaceRunRow
    """

    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Execution type discriminator
    execution_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Feature-specific fields
    feature_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    entry_skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workspace_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Unified status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    # Request / result
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Graph topology (static, set at start or discovered early)
    graph_structure: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Node states (dynamic, updated during execution)
    node_states: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    runtime_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifact_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    next_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    advisory_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parent-child for nested executions
    parent_execution_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("executions.id"),
        nullable=True,
    )
    child_execution_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Dispatch tracking
    dispatch_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    worker_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_executions_user_status", "user_id", "status"),
        Index("ix_executions_workspace_feature_status", "workspace_id", "feature_id", "status"),
        Index("ix_executions_thread_created", "thread_id", "created_at"),
        Index("ix_executions_parent", "parent_execution_id"),
        Index("ix_executions_type_status", "execution_type", "status"),
    )
