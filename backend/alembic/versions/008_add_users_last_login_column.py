"""add users.last_login column

Revision ID: 008_add_users_last_login
Revises: 007_chat_thread_model_default
Create Date: 2026-03-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_users_last_login"
down_revision: Union[str, None] = "007_chat_thread_model_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable last_login timestamp to users."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}
    if "last_login" not in existing_columns:
        op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop users.last_login."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}
    if "last_login" in existing_columns:
        op.drop_column("users", "last_login")
