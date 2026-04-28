"""add compute sessions

Revision ID: 027_add_compute_sessions
Revises: 026_add_task_active_dedupe_index
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027_add_compute_sessions"
down_revision: str | None = "026_add_task_active_dedupe_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create compute_sessions table."""
    op.create_table(
        "compute_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_session_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_session_id", sa.String(length=100), nullable=True),
        sa.Column("active_view", sa.String(length=50), nullable=False),
        sa.Column(
            "ui_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_session_id"],
            ["execution_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compute_sessions_execution_session",
        "compute_sessions",
        ["execution_session_id"],
        unique=True,
    )
    op.create_index(
        "ix_compute_sessions_workspace_id",
        "compute_sessions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_compute_sessions_user_id",
        "compute_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_compute_sessions_workspace_updated",
        "compute_sessions",
        ["workspace_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_compute_sessions_user_workspace_updated",
        "compute_sessions",
        ["user_id", "workspace_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop compute_sessions table."""
    op.drop_index("ix_compute_sessions_user_workspace_updated", table_name="compute_sessions")
    op.drop_index("ix_compute_sessions_workspace_updated", table_name="compute_sessions")
    op.drop_index("ix_compute_sessions_user_id", table_name="compute_sessions")
    op.drop_index("ix_compute_sessions_workspace_id", table_name="compute_sessions")
    op.drop_index("ix_compute_sessions_execution_session", table_name="compute_sessions")
    op.drop_table("compute_sessions")

