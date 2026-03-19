"""add users refresh token tracking

Revision ID: 009_add_refresh_token_tracking
Revises: 008_add_users_last_login
Create Date: 2026-03-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_refresh_token_tracking"
down_revision: Union[str, None] = "008_add_users_last_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable refresh token tracking fields to users."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    if "refresh_token_hash" not in existing_columns:
        op.add_column("users", sa.Column("refresh_token_hash", sa.String(length=64), nullable=True))

    if "refresh_token_expires_at" not in existing_columns:
        op.add_column("users", sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop refresh token tracking fields from users."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    if "refresh_token_expires_at" in existing_columns:
        op.drop_column("users", "refresh_token_expires_at")

    if "refresh_token_hash" in existing_columns:
        op.drop_column("users", "refresh_token_hash")
