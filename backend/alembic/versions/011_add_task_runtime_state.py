"""add task runtime state column

Revision ID: 011_add_task_runtime_state
Revises: 010_add_chat_thread_skill
Create Date: 2026-03-20

Adds a JSONB column on task_records so long-running task runtime blocks can be
persisted across refreshes and reconnects.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "011_add_task_runtime_state"
down_revision: Union[str, None] = "010_add_chat_thread_skill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add runtime_state column to task_records."""
    op.add_column(
        "task_records",
        sa.Column("runtime_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop runtime_state column from task_records."""
    op.drop_column("task_records", "runtime_state")
