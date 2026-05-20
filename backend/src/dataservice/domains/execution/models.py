"""Execution domain storage models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin
from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord


class ExecutionEventRecord(Base, UUIDMixin, TimestampMixin):
    """Ordered event emitted by an execution or execution node."""

    __tablename__ = "execution_events"
    __table_args__ = (
        Index("ix_execution_events_execution_sequence", "execution_id", "sequence_index", unique=True),
        Index("ix_execution_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_execution_events_type_created", "event_type", "created_at"),
    )

    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "ExecutionEventRecord",
    "ExecutionNodeRecord",
    "ExecutionRecord",
]
