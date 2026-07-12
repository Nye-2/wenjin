"""create canonical Mission Runtime persistence and drop execution-era stores

Revision ID: 086_mission_runtime_cutover
Revises: 085_single_gpt55_runtime
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "086_mission_runtime_cutover"
down_revision: str | None = "085_single_gpt55_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MISSION_STATUSES = "'created', 'planning', 'running', 'waiting', 'completed', 'failed', 'cancelled'"
_REVIEW_STATUSES = "'pending', 'accepted', 'rejected', 'needs_more_evidence', 'committed', 'superseded'"
_COMMIT_STATUSES = "'pending', 'applying', 'committed', 'failed', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "mission_runs",
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("parent_mission_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_type", sa.String(length=50), nullable=False),
        sa.Column("mission_policy_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="created", nullable=False),
        sa.Column(
            "review_mode",
            sa.String(length=32),
            server_default="balanced_default",
            nullable=False,
        ),
        sa.Column("active_stage_id", sa.String(length=120), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=16), nullable=False),
        sa.Column(
            "snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "runtime_context_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("context_checkpoint_ref", sa.Text(), nullable=True),
        sa.Column("pending_review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("artifact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_subagent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mission_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("last_command_seq", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "last_applied_command_seq", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("next_wakeup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_epoch", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_item_seq", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({_MISSION_STATUSES})", name="ck_mission_runs_status"),
        sa.CheckConstraint(
            "review_mode IN ('review_all', 'balanced_default', 'auto_draft')",
            name="ck_mission_runs_review_mode",
        ),
        sa.CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high', 'xhigh')",
            name="ck_mission_runs_reasoning_effort",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_mission_runs_state_version"),
        sa.CheckConstraint("last_item_seq >= 0", name="ck_mission_runs_last_item_seq"),
        sa.CheckConstraint("lease_epoch >= 0", name="ck_mission_runs_lease_epoch"),
        sa.CheckConstraint(
            "last_command_seq >= 0 AND last_applied_command_seq >= 0 "
            "AND last_command_seq >= last_applied_command_seq",
            name="ck_mission_runs_command_cursor",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_mission_runs_lease_pair",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed', 'failed', 'cancelled') OR "
            "(lease_owner IS NULL AND lease_expires_at IS NULL AND next_wakeup_at IS NULL)",
            name="ck_mission_runs_terminal_quiescent",
        ),
        sa.CheckConstraint(
            "pending_review_count >= 0 AND evidence_count >= 0 "
            "AND artifact_count >= 0 AND active_subagent_count >= 0",
            name="ck_mission_runs_nonnegative_counts",
        ),
        sa.ForeignKeyConstraint(
            ["parent_mission_id"],
            ["mission_runs.mission_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("mission_id"),
    )
    op.create_index(
        "uq_mission_runs_workspace_idempotency",
        "mission_runs",
        ["workspace_id", "mission_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("mission_idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_mission_runs_workspace_updated",
        "mission_runs",
        ["workspace_id", sa.text("updated_at DESC")],
    )
    op.create_index(
        "ix_mission_runs_thread_created",
        "mission_runs",
        ["thread_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_mission_runs_scheduler",
        "mission_runs",
        ["status", "next_wakeup_at", "lease_expires_at"],
    )
    op.create_index(
        "uq_mission_runs_thread_foreground",
        "mission_runs",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text(
            "thread_id IS NOT NULL AND status IN ('created', 'planning', 'running', 'waiting')"
        ),
    )

    op.create_table(
        "mission_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.String(length=80), nullable=False),
        sa.Column("operation_id", sa.String(length=160), nullable=True),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("stage_id", sa.String(length=120), nullable=True),
        sa.Column("producer", sa.String(length=160), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "phase IN ('started', 'progress', 'completed', 'failed', 'cancelled')",
            name="ck_mission_items_phase",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mission_runs.mission_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "seq", name="uq_mission_items_mission_seq"),
    )
    op.create_index(
        "ix_mission_items_type_stage_seq",
        "mission_items",
        ["mission_id", "item_type", "stage_id", sa.text("seq DESC")],
    )
    op.create_index(
        "ix_mission_items_operation_seq",
        "mission_items",
        ["mission_id", "operation_id", "seq"],
        postgresql_where=sa.text("operation_id IS NOT NULL"),
    )

    op.create_table(
        "mission_review_items",
        sa.Column("review_item_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("source_item_seq", sa.BigInteger(), nullable=True),
        sa.Column("target_kind", sa.String(length=80), nullable=False),
        sa.Column("target_room", sa.String(length=80), nullable=True),
        sa.Column("target_ref", sa.Text(), nullable=True),
        sa.Column("base_revision_ref", sa.Text(), nullable=True),
        sa.Column("base_hash", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("review_required_reason", sa.Text(), nullable=True),
        sa.Column(
            "preview_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("preview_ref", sa.Text(), nullable=True),
        sa.Column("preview_hash", sa.String(length=128), nullable=True),
        sa.Column("preview_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decided_by", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_REVIEW_STATUSES})", name="ck_mission_review_items_status"
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_mission_review_items_risk",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mission_runs.mission_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("review_item_id"),
    )
    op.create_index(
        "ix_mission_review_items_status_risk",
        "mission_review_items",
        ["mission_id", "status", "risk_level"],
    )
    op.create_index(
        "ix_mission_review_items_target_room",
        "mission_review_items",
        ["mission_id", "target_room"],
    )

    op.create_table(
        "mission_commits",
        sa.Column("commit_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("review_item_id", sa.String(length=36), nullable=False),
        sa.Column("commit_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "targets_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"status IN ({_COMMIT_STATUSES})", name="ck_mission_commits_status"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_mission_commits_attempt_count"),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mission_runs.mission_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["mission_review_items.review_item_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("commit_id"),
        sa.UniqueConstraint("mission_id", "commit_key", name="uq_mission_commits_key"),
        sa.UniqueConstraint("review_item_id", name="uq_mission_commits_review_item"),
    )
    op.create_index(
        "ix_mission_commits_status", "mission_commits", ["mission_id", "status"]
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_mission_item_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'mission_items are immutable after append';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_mission_items_immutable
        BEFORE UPDATE ON mission_items
        FOR EACH ROW EXECUTE FUNCTION reject_mission_item_update()
        """
    )

    # Development clean cut: these stores are not runtime compatibility inputs.
    for table_name in (
        "subagent_task_records",
        "compute_sessions",
        "execution_events",
        "execution_nodes",
        "review_action_logs",
        "review_items",
        "review_batches",
        "run_history",
        "executions",
        "dataservice_outbox_events",
        "dataservice_idempotency_keys",
        "dataservice_migration_reports",
    ):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))


def downgrade() -> None:
    raise RuntimeError(
        "086_mission_runtime_cutover is an irreversible development clean cut; reseed instead"
    )
