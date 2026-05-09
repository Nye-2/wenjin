"""Create workspace_tasks table.

Revision ID: 039_create_workspace_tasks
Revises: 038_create_sandboxes
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "039_create_workspace_tasks"
down_revision = "038_create_sandboxes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("related_execution_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workspace_tasks_active",
        "workspace_tasks",
        ["workspace_id", "status", sa.text("priority DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_tasks_active", table_name="workspace_tasks")
    op.drop_table("workspace_tasks")
