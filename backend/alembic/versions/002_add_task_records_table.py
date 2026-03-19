"""add task_records table

Revision ID: 002_task_records
Revises: 20260309_toc
Create Date: 2026-03-11

Creates the task_records table for the async task system.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002_task_records"
down_revision: Union[str, None] = "20260309_toc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create task_records table."""
    op.create_table(
        "task_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="5"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes
    op.create_index("ix_task_records_user_id", "task_records", ["user_id"])
    op.create_index("ix_task_records_task_type", "task_records", ["task_type"])
    op.create_index("ix_task_records_status", "task_records", ["status"])
    op.create_index("ix_task_records_user_status", "task_records", ["user_id", "status"])
    op.create_index("ix_task_records_created_at", "task_records", ["created_at"])


def downgrade() -> None:
    """Drop task_records table."""
    op.drop_index("ix_task_records_created_at", table_name="task_records")
    op.drop_index("ix_task_records_user_status", table_name="task_records")
    op.drop_index("ix_task_records_status", table_name="task_records")
    op.drop_index("ix_task_records_task_type", table_name="task_records")
    op.drop_index("ix_task_records_user_id", table_name="task_records")
    op.drop_table("task_records")
