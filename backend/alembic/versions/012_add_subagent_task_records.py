"""add durable subagent task records

Revision ID: 012_add_subagent_task_records
Revises: 011_add_task_runtime_state
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "012_add_subagent_task_records"
down_revision: Union[str, None] = "011_add_task_runtime_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create durable subagent lifecycle records."""
    op.create_table(
        "subagent_task_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("subagent_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("output_preview", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "task_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subagent_task_records_workspace_updated",
        "subagent_task_records",
        ["workspace_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subagent_task_records_workspace_id"),
        "subagent_task_records",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_subagent_task_records_thread_created",
        "subagent_task_records",
        ["thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subagent_task_records_thread_id"),
        "subagent_task_records",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_subagent_task_records_user_created",
        "subagent_task_records",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subagent_task_records_user_id"),
        "subagent_task_records",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop durable subagent lifecycle records."""
    op.drop_index(op.f("ix_subagent_task_records_user_id"), table_name="subagent_task_records")
    op.drop_index("ix_subagent_task_records_user_created", table_name="subagent_task_records")
    op.drop_index(op.f("ix_subagent_task_records_thread_id"), table_name="subagent_task_records")
    op.drop_index("ix_subagent_task_records_thread_created", table_name="subagent_task_records")
    op.drop_index(op.f("ix_subagent_task_records_workspace_id"), table_name="subagent_task_records")
    op.drop_index("ix_subagent_task_records_workspace_updated", table_name="subagent_task_records")
    op.drop_table("subagent_task_records")
