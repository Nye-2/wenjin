"""Compute work-plane session model."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, generate_uuid


class ComputeSessionRecord(Base):
    """Persistent UI/work-plane binding for an execution.

    This record is intentionally not a business-state source of truth. Feature
    lifecycle lives in ExecutionRecord; compute_sessions stores rebuildable
    workbench shell state needed to restore the stage.
    """

    __tablename__ = "compute_sessions"
    __table_args__ = (
        Index("ix_compute_sessions_execution", "execution_id", unique=True),
        Index("ix_compute_sessions_workspace_updated", "workspace_id", "updated_at"),
        Index(
            "ix_compute_sessions_user_workspace_updated",
            "user_id",
            "workspace_id",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sandbox_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active_view: Mapped[str] = mapped_column(String(50), nullable=False, default="overview")
    ui_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
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

    def __repr__(self) -> str:
        return (
            f"<ComputeSessionRecord(id={self.id}, "
            f"execution_id={self.execution_id})>"
        )
