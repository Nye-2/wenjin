"""create workspace_run table

Revision ID: 17aa92618744
Revises: 03f821b6953f
Create Date: 2026-05-07 09:16:59.052438+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "17aa92618744"
down_revision: Union[str, None] = "03f821b6953f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "workspace_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("thread_id", sa.String(length=36), sa.ForeignKey("threads.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_card", sa.JSON(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspace_run_thread_started", "workspace_run", ["thread_id", "started_at"])
    op.add_column("subagent_task_records", sa.Column("run_id", sa.String(length=36), sa.ForeignKey("workspace_run.id"), nullable=True))


def downgrade():
    op.drop_column("subagent_task_records", "run_id")
    op.drop_index("ix_workspace_run_thread_started", table_name="workspace_run")
    op.drop_table("workspace_run")
