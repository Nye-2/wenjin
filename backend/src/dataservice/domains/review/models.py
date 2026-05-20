"""Review batch storage models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class ReviewBatchRecord(Base, UUIDMixin, TimestampMixin):
    """A user-reviewable package of staged outputs."""

    __tablename__ = "review_batches"
    __table_args__ = (
        Index("ix_review_batches_workspace_status", "workspace_id", "status"),
        Index("ix_review_batches_execution", "execution_id"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="review_batch.v1",
        server_default="review_batch.v1",
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class ReviewItemRecord(Base, UUIDMixin, TimestampMixin):
    """One reviewable item within a batch."""

    __tablename__ = "review_items"
    __table_args__ = (
        Index("ix_review_items_batch_status", "batch_id", "status"),
        Index("ix_review_items_workspace_status", "workspace_id", "status"),
        Index("ix_review_items_target", "target_domain", "target_kind"),
    )

    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ref_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    preview_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewActionLogRecord(Base, UUIDMixin, TimestampMixin):
    """Append-only audit log for review state transitions."""

    __tablename__ = "review_action_logs"
    __table_args__ = (
        Index("ix_review_action_logs_batch_created", "batch_id", "created_at"),
        Index("ix_review_action_logs_item_created", "item_id", "created_at"),
    )

    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("review_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
