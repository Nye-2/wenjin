"""subagent_task add criticality column

Revision ID: 03f821b6953f
Revises: 028_reference_library_rebuild
Create Date: 2026-05-07 09:11:25.426456+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "03f821b6953f"
down_revision: Union[str, None] = "028_reference_library_rebuild"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subagent_task_records",
        sa.Column("criticality", sa.String(length=8), nullable=False, server_default="low"),
    )


def downgrade() -> None:
    op.drop_column("subagent_task_records", "criticality")
