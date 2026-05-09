"""Create run_history table.

Revision ID: 037_create_run_history
Revises: 036_create_memory_facts
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "037_create_run_history"
down_revision = "036_create_memory_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("execution_id", sa.String(36), nullable=False, unique=True),
        sa.Column("capability_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("artifact_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("token_usage", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_run_history_ws",
        "run_history",
        ["workspace_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_run_history_ws", table_name="run_history")
    op.drop_table("run_history")
