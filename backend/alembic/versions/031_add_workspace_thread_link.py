"""Add thread_id 1:1 link to workspaces.

Revision ID: 031_add_workspace_thread_link
Revises: 030_create_executions_and_execution_nodes
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "031_add_workspace_thread_link"
down_revision = "030_create_executions_and_execution_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("thread_id", sa.String(36), nullable=True),
    )
    op.create_unique_constraint(
        "uq_workspaces_thread_id", "workspaces", ["thread_id"]
    )
    op.create_foreign_key(
        "fk_workspaces_thread_id", "workspaces", "threads",
        ["thread_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_workspaces_thread_id", "workspaces", type_="foreignkey")
    op.drop_constraint("uq_workspaces_thread_id", "workspaces", type_="unique")
    op.drop_column("workspaces", "thread_id")
