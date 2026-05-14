"""drop execution_sessions legacy schema

Revision ID: 048_drop_execution_sessions_legacy
Revises: 047_execution_id_hard_cut
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "048_drop_execution_sessions_legacy"
down_revision: str | None = "047_execution_id_hard_cut"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Remove execution-session legacy objects after the execution hard cut."""
    if _has_column("reference_usage_events", "execution_session_id"):
        op.alter_column(
            "reference_usage_events",
            "execution_session_id",
            new_column_name="execution_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    if _has_table("subagent_task_records") and _has_index(
        "subagent_task_records",
        "ix_subagent_task_records_execution_session_id",
    ):
        op.drop_index(
            "ix_subagent_task_records_execution_session_id",
            table_name="subagent_task_records",
        )

    if _has_table("execution_sessions"):
        for index_name in (
            "ix_execution_sessions_status",
            "ix_execution_sessions_primary_task_id",
            "ix_execution_sessions_thread_created",
            "ix_execution_sessions_workspace_updated",
            "ix_execution_sessions_feature_id",
            "ix_execution_sessions_thread_id",
            "ix_execution_sessions_workspace_id",
            "ix_execution_sessions_user_id",
            "ix_execution_sessions_user_workspace_updated",
        ):
            if _has_index("execution_sessions", index_name):
                op.drop_index(index_name, table_name="execution_sessions")
        op.drop_table("execution_sessions")


def downgrade() -> None:
    """Recreate execution-session legacy objects."""
    op.create_table(
        "execution_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_type", sa.String(length=50), nullable=False),
        sa.Column("feature_id", sa.String(length=100), nullable=False),
        sa.Column("entry_skill_id", sa.String(length=100), nullable=True),
        sa.Column("launch_source", sa.String(length=20), nullable=False),
        sa.Column("launch_message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("task_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("primary_task_id", sa.String(length=36), nullable=True),
        sa.Column("runtime_snapshot", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("next_actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("advisory_code", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_sessions_user_id", "execution_sessions", ["user_id"])
    op.create_index("ix_execution_sessions_workspace_id", "execution_sessions", ["workspace_id"])
    op.create_index("ix_execution_sessions_thread_id", "execution_sessions", ["thread_id"])
    op.create_index("ix_execution_sessions_feature_id", "execution_sessions", ["feature_id"])
    op.create_index(
        "ix_execution_sessions_workspace_updated",
        "execution_sessions",
        ["workspace_id", "updated_at"],
    )
    op.create_index(
        "ix_execution_sessions_user_workspace_updated",
        "execution_sessions",
        ["user_id", "workspace_id", "updated_at"],
    )
    op.create_index(
        "ix_execution_sessions_thread_created",
        "execution_sessions",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "ix_execution_sessions_primary_task_id",
        "execution_sessions",
        ["primary_task_id"],
    )
    op.create_index("ix_execution_sessions_status", "execution_sessions", ["status"])

    if _has_table("subagent_task_records"):
        op.create_index(
            "ix_subagent_task_records_execution_session_id",
            "subagent_task_records",
            ["execution_id"],
        )

    if _has_column("reference_usage_events", "execution_id"):
        op.alter_column(
            "reference_usage_events",
            "execution_id",
            new_column_name="execution_session_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
