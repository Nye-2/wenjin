"""add foreign key from subagent tasks to execution sessions

Revision ID: 021_subagent_exec_fk
Revises: 020_subagent_exec_required
Create Date: 2026-04-10
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_subagent_exec_fk"
down_revision: Union[str, None] = "020_subagent_exec_required"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce execution session referential integrity for subagent records."""
    op.execute(
        "DELETE FROM subagent_task_records s "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM execution_sessions e WHERE e.id = s.execution_session_id"
        ")"
    )
    op.create_foreign_key(
        "fk_subagent_task_exec_session",
        "subagent_task_records",
        "execution_sessions",
        ["execution_session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove execution session foreign key from subagent task records."""
    op.drop_constraint(
        "fk_subagent_task_exec_session",
        "subagent_task_records",
        type_="foreignkey",
    )
