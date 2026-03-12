"""add chat_threads table

Revision ID: 003_chat_threads
Revises: 002_task_records
Create Date: 2026-03-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "003_chat_threads"
down_revision: Union[str, None] = "002_task_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create chat_threads table."""
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "model",
            sa.String(100),
            nullable=False,
            server_default="gpt-4o",
        ),
        sa.Column(
            "messages",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
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

    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])
    op.create_index("ix_chat_threads_workspace_id", "chat_threads", ["workspace_id"])
    op.create_index(
        "ix_chat_threads_user_updated",
        "chat_threads",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    """Drop chat_threads table."""
    op.drop_index("ix_chat_threads_user_updated", table_name="chat_threads")
    op.drop_index("ix_chat_threads_workspace_id", table_name="chat_threads")
    op.drop_index("ix_chat_threads_user_id", table_name="chat_threads")
    op.drop_table("chat_threads")
