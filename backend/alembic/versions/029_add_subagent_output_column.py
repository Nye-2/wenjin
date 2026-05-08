"""add output column to subagent_task_records

Revision ID: 029_add_subagent_output
Revises: 17aa92618744
Create Date: 2026-05-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "029_add_subagent_output"
down_revision: Union[str, None] = "17aa92618744"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subagent_task_records",
        sa.Column("output", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subagent_task_records", "output")
