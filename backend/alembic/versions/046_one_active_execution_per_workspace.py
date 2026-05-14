"""one active execution per workspace

Revision ID: 046_one_active_execution
Revises: 43d4f1cda00b
Create Date: 2026-05-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "046_one_active_execution"
down_revision: Union[str, None] = "43d4f1cda00b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_index(
        "uq_executions_one_active_per_workspace",
        "executions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text(
            "(workspace_id IS NOT NULL) AND "
            "(status IN ('pending', 'running', 'cancelling'))"
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(
        "uq_executions_one_active_per_workspace",
        table_name="executions",
    )
