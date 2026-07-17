"""Canonical persistence models for the Mission Runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, generate_uuid

MISSION_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")

MISSION_STATUSES = (
    "created",
    "planning",
    "running",
    "waiting",
    "completed",
    "failed",
    "cancelled",
)
MISSION_ITEM_PHASES = ("started", "progress", "completed", "failed", "cancelled")
MISSION_REVIEW_STATUSES = (
    "pending",
    "accepted",
    "rejected",
    "needs_more_evidence",
    "committed",
    "superseded",
)
MISSION_COMMIT_STATUSES = ("pending", "applying", "committed", "failed", "cancelled")
MISSION_REVIEW_MODES = ("review_all", "balanced_default", "auto_draft")
MISSION_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class MissionRunRecord(Base):
    """Durable lifecycle aggregate and bounded recovery snapshot."""

    __tablename__ = "mission_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(MISSION_STATUSES)})",
            name="ck_mission_runs_status",
        ),
        CheckConstraint(
            f"review_mode IN ({_sql_values(MISSION_REVIEW_MODES)})",
            name="ck_mission_runs_review_mode",
        ),
        CheckConstraint(
            f"reasoning_effort IN ({_sql_values(MISSION_REASONING_EFFORTS)})",
            name="ck_mission_runs_reasoning_effort",
        ),
        CheckConstraint("state_version >= 0", name="ck_mission_runs_state_version"),
        CheckConstraint("last_item_seq >= 0", name="ck_mission_runs_last_item_seq"),
        CheckConstraint("lease_epoch >= 0", name="ck_mission_runs_lease_epoch"),
        CheckConstraint("dispatch_epoch >= 0", name="ck_mission_runs_dispatch_epoch"),
        CheckConstraint(
            "last_command_seq >= 0 AND last_applied_command_seq >= 0 "
            "AND last_command_seq >= last_applied_command_seq",
            name="ck_mission_runs_command_cursor",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_mission_runs_lease_pair",
        ),
        CheckConstraint(
            "(dispatch_owner IS NULL AND dispatch_expires_at IS NULL) OR "
            "(dispatch_owner IS NOT NULL AND dispatch_expires_at IS NOT NULL)",
            name="ck_mission_runs_dispatch_pair",
        ),
        CheckConstraint(
            "status NOT IN ('completed', 'failed', 'cancelled') OR "
            "(lease_owner IS NULL AND lease_expires_at IS NULL "
            "AND dispatch_owner IS NULL AND dispatch_expires_at IS NULL "
            "AND next_wakeup_at IS NULL)",
            name="ck_mission_runs_terminal_quiescent",
        ),
        CheckConstraint(
            "pending_review_count >= 0 AND evidence_count >= 0 "
            "AND artifact_count >= 0 AND active_subagent_count >= 0",
            name="ck_mission_runs_nonnegative_counts",
        ),
        Index(
            "uq_mission_runs_workspace_idempotency",
            "workspace_id",
            "mission_idempotency_key",
            unique=True,
            postgresql_where=text("mission_idempotency_key IS NOT NULL"),
            sqlite_where=text("mission_idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_mission_runs_workspace_updated_mission",
            "workspace_id",
            "updated_at",
            "mission_id",
        ),
        Index(
            "ix_mission_runs_user_updated_mission",
            "user_id",
            "updated_at",
            "mission_id",
        ),
        Index("ix_mission_runs_thread_created", "thread_id", "created_at"),
        Index(
            "ix_mission_runs_due_wakeup",
            "next_wakeup_at",
            "dispatch_expires_at",
            postgresql_where=text(
                "status IN ('created', 'planning', 'running', 'waiting') "
                "AND next_wakeup_at IS NOT NULL"
            ),
            sqlite_where=text(
                "status IN ('created', 'planning', 'running', 'waiting') "
                "AND next_wakeup_at IS NOT NULL"
            ),
        ),
        Index(
            "ix_mission_runs_expired_driver",
            "lease_expires_at",
            "dispatch_expires_at",
            postgresql_where=text(
                "status IN ('created', 'planning', 'running', 'waiting') "
                "AND lease_expires_at IS NOT NULL"
            ),
            sqlite_where=text(
                "status IN ('created', 'planning', 'running', 'waiting') "
                "AND lease_expires_at IS NOT NULL"
            ),
        ),
        Index(
            "uq_mission_runs_thread_foreground",
            "thread_id",
            unique=True,
            postgresql_where=text(
                "thread_id IS NOT NULL AND status IN "
                "('created', 'planning', 'running', 'waiting')"
            ),
            sqlite_where=text(
                "thread_id IS NOT NULL AND status IN "
                "('created', 'planning', 'running', 'waiting')"
            ),
        ),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    parent_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mission_policy_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created", server_default="created"
    )
    review_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="balanced_default",
        server_default="balanced_default",
    )
    active_stage_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        MISSION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    runtime_context_json: Mapped[dict[str, Any]] = mapped_column(
        MISSION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    context_checkpoint_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    artifact_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    active_subagent_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    mission_idempotency_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    last_command_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    last_applied_command_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    next_wakeup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lease_epoch: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatch_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dispatch_epoch: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    dispatch_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    last_item_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MissionItemRecord(Base):
    """Append-only semantic ledger item for one mission."""

    __tablename__ = "mission_items"
    __table_args__ = (
        CheckConstraint(
            f"phase IN ({_sql_values(MISSION_ITEM_PHASES)})",
            name="ck_mission_items_phase",
        ),
        UniqueConstraint("mission_id", "seq", name="uq_mission_items_mission_seq"),
        Index(
            "ix_mission_items_type_stage_seq",
            "mission_id",
            "item_type",
            "stage_id",
            "seq",
        ),
        Index(
            "ix_mission_items_operation_seq",
            "mission_id",
            "operation_id",
            "seq",
            postgresql_where=text("operation_id IS NOT NULL"),
            sqlite_where=text("operation_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_type: Mapped[str] = mapped_column(String(80), nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    stage_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    producer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MISSION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MissionReviewItemRecord(Base):
    """Atomic workspace-write candidate and its current review decision."""

    __tablename__ = "mission_review_items"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(MISSION_REVIEW_STATUSES)})",
            name="ck_mission_review_items_status",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_mission_review_items_risk",
        ),
        Index(
            "ix_mission_review_items_status_risk",
            "mission_id",
            "status",
            "risk_level",
        ),
        Index("ix_mission_review_items_target_room", "mission_id", "target_room"),
        Index("ix_mission_review_items_output", "mission_id", "output_key", "created_at"),
        UniqueConstraint(
            "mission_id",
            "review_item_id",
            name="uq_mission_review_items_mission_item",
        ),
        ForeignKeyConstraint(
            ["mission_id", "source_item_seq"],
            ["mission_items.mission_id", "mission_items.seq"],
            name="fk_mission_review_items_source_item",
        ),
    )

    review_item_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_item_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_key: Mapped[str] = mapped_column(String(160), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    target_room: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_revision_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    review_required_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_json: Mapped[dict[str, Any]] = mapped_column(
        MISSION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    preview_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    preview_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_json: Mapped[dict[str, Any] | None] = mapped_column(
        MISSION_JSON_TYPE, nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MissionCommitRecord(Base):
    """Idempotent application record for one accepted review item."""

    __tablename__ = "mission_commits"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(MISSION_COMMIT_STATUSES)})",
            name="ck_mission_commits_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_mission_commits_attempt_count"),
        UniqueConstraint("mission_id", "commit_key", name="uq_mission_commits_key"),
        UniqueConstraint("review_item_id", name="uq_mission_commits_review_item"),
        ForeignKeyConstraint(
            ["mission_id", "review_item_id"],
            ["mission_review_items.mission_id", "mission_review_items.review_item_id"],
            name="fk_mission_commits_review_item",
            ondelete="CASCADE",
        ),
        Index("ix_mission_commits_status", "mission_id", "status"),
        Index(
            "ix_mission_commits_applying_expiry",
            "attempt_expires_at",
            postgresql_where=text("status = 'applying'"),
        ),
    )

    commit_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    mission_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    review_item_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    commit_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    targets_json: Mapped[dict[str, Any]] = mapped_column(
        MISSION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    error_json: Mapped[dict[str, Any] | None] = mapped_column(
        MISSION_JSON_TYPE, nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    attempt_token: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attempt_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MissionItemImmutableError(RuntimeError):
    """Raised when application code attempts to mutate an appended ledger row."""


@event.listens_for(MissionItemRecord, "before_update")
def _reject_mission_item_update(*_: object) -> None:
    raise MissionItemImmutableError("MissionItem rows are immutable after append")


__all__ = [
    "MISSION_COMMIT_STATUSES",
    "MISSION_ITEM_PHASES",
    "MISSION_REASONING_EFFORTS",
    "MISSION_REVIEW_MODES",
    "MISSION_REVIEW_STATUSES",
    "MISSION_STATUSES",
    "MissionCommitRecord",
    "MissionItemImmutableError",
    "MissionItemRecord",
    "MissionReviewItemRecord",
    "MissionRunRecord",
]
