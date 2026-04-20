"""add execution session link to subagent task records

Revision ID: 019_subagent_exec_link
Revises: 018_add_execution_sessions
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_subagent_exec_link"
down_revision: Union[str, None] = "018_add_execution_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist strong execution-session linkage for subagent records."""
    op.add_column(
        "subagent_task_records",
        sa.Column("execution_session_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_subagent_task_records_execution_session_id"),
        "subagent_task_records",
        ["execution_session_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop strong execution-session linkage for subagent records."""
    op.drop_index(
        op.f("ix_subagent_task_records_execution_session_id"),
        table_name="subagent_task_records",
    )
    op.drop_column("subagent_task_records", "execution_session_id")
