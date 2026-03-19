"""add chat thread skill column

Revision ID: 010_add_chat_thread_skill
Revises: 009_add_refresh_token_tracking
Create Date: 2026-03-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_add_chat_thread_skill"
down_revision: Union[str, None] = "009_add_refresh_token_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable selected skill column to chat threads."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("chat_threads")}

    if "skill" not in existing_columns:
        op.add_column("chat_threads", sa.Column("skill", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Drop selected skill column from chat threads."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("chat_threads")}

    if "skill" in existing_columns:
        op.drop_column("chat_threads", "skill")
