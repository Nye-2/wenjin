"""add_execution_display_name

Revision ID: 43d4f1cda00b
Revises: 044_unarchive_workspace_references
Create Date: 2026-05-12 09:29:20.113532+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43d4f1cda00b'
down_revision: Union[str, None] = '044_unarchive_workspace_references'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column("executions", sa.Column("display_name", sa.String(200), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("executions", "display_name")
