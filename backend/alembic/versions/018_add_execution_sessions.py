"""add execution sessions

Revision ID: 018_add_execution_sessions
Revises: 017_add_latex_core_tables
Create Date: 2026-04-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "018_add_execution_sessions"
down_revision: Union[str, None] = "017_add_latex_core_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create execution session aggregate table and task linkage."""
    op.add_column(
        "task_records",
        sa.Column("execution_session_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_task_records_execution_session_id"),
        "task_records",
        ["execution_session_id"],
        unique=False,
    )

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
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "task_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("primary_task_id", sa.String(length=36), nullable=True),
        sa.Column(
            "runtime_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column(
            "artifact_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "next_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("advisory_code", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_sessions_user_id"),
        "execution_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_sessions_workspace_id"),
        "execution_sessions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_sessions_thread_id"),
        "execution_sessions",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_sessions_feature_id"),
        "execution_sessions",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_sessions_workspace_updated",
        "execution_sessions",
        ["workspace_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_sessions_thread_created",
        "execution_sessions",
        ["thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_sessions_primary_task_id",
        "execution_sessions",
        ["primary_task_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_sessions_status",
        "execution_sessions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop execution session aggregate table and task linkage."""
    op.drop_index("ix_execution_sessions_status", table_name="execution_sessions")
    op.drop_index("ix_execution_sessions_primary_task_id", table_name="execution_sessions")
    op.drop_index("ix_execution_sessions_thread_created", table_name="execution_sessions")
    op.drop_index("ix_execution_sessions_workspace_updated", table_name="execution_sessions")
    op.drop_index(op.f("ix_execution_sessions_feature_id"), table_name="execution_sessions")
    op.drop_index(op.f("ix_execution_sessions_thread_id"), table_name="execution_sessions")
    op.drop_index(op.f("ix_execution_sessions_workspace_id"), table_name="execution_sessions")
    op.drop_index(op.f("ix_execution_sessions_user_id"), table_name="execution_sessions")
    op.drop_table("execution_sessions")

    op.drop_index(op.f("ix_task_records_execution_session_id"), table_name="task_records")
    op.drop_column("task_records", "execution_session_id")
