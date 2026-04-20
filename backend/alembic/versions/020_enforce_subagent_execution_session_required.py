"""enforce execution session linkage on subagent task records

Revision ID: 020_subagent_exec_required
Revises: 019_subagent_exec_link
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_subagent_exec_required"
down_revision: Union[str, None] = "019_subagent_exec_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop unlinked legacy rows and enforce non-null execution linkage."""
    op.execute(
        "DELETE FROM subagent_task_records "
        "WHERE execution_session_id IS NULL OR TRIM(execution_session_id) = ''"
    )
    op.alter_column(
        "subagent_task_records",
        "execution_session_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )


def downgrade() -> None:
    """Allow nullable execution linkage on subagent records again."""
    op.alter_column(
        "subagent_task_records",
        "execution_session_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
