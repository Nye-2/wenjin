"""add workspace_literature table

Revision ID: 004_workspace_literature
Revises: 003_chat_threads
Create Date: 2026-03-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "004_workspace_literature"
down_revision: Union[str, None] = "003_chat_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace_literature table."""
    op.create_table(
        "workspace_literature",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column(
            "authors",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("citations", sa.Integer, nullable=True),
        sa.Column("venue", sa.String(300), nullable=True),
        sa.Column("quartile", sa.String(10), nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("doi", sa.String(200), nullable=True),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "is_core",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_workspace_literature_workspace_id", "workspace_literature", ["workspace_id"])


def downgrade() -> None:
    """Drop workspace_literature table."""
    op.drop_index("ix_workspace_literature_workspace_id", table_name="workspace_literature")
    op.drop_table("workspace_literature")
