"""hard cut execution_session_id to execution_id

Revision ID: 047_execution_id_hard_cut
Revises: 046_one_active_execution
Create Date: 2026-05-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "047_execution_id_hard_cut"
down_revision: Union[str, None] = "046_one_active_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.alter_column("task_records", "execution_session_id", new_column_name="execution_id")
    op.alter_column("compute_sessions", "execution_session_id", new_column_name="execution_id")
    op.drop_column("subagent_task_records", "execution_session_id")

    op.drop_constraint(
        "compute_sessions_execution_session_id_fkey",
        "compute_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "compute_sessions_execution_id_fkey",
        "compute_sessions",
        "executions",
        ["execution_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index("ix_compute_sessions_execution_session", table_name="compute_sessions")
    op.create_index(
        "ix_compute_sessions_execution",
        "compute_sessions",
        ["execution_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("ix_compute_sessions_execution", table_name="compute_sessions")
    op.drop_constraint(
        "compute_sessions_execution_id_fkey",
        "compute_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "compute_sessions_execution_session_id_fkey",
        "compute_sessions",
        "execution_sessions",
        ["execution_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_compute_sessions_execution_session",
        "compute_sessions",
        ["execution_id"],
        unique=True,
    )

    op.alter_column("compute_sessions", "execution_id", new_column_name="execution_session_id")
    op.alter_column("task_records", "execution_id", new_column_name="execution_session_id")
    op.add_column(
        "subagent_task_records",
        sa.Column("execution_session_id", sa.String(length=36), nullable=True),
    )
