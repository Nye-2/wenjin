"""normalize chat thread model default alias

Revision ID: 007_chat_thread_model_default
Revises: 006_artifact_version_unique
Create Date: 2026-03-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_chat_thread_model_default"
down_revision: Union[str, None] = "006_artifact_version_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Use logical alias for DB-level chat thread model default."""
    op.alter_column(
        "chat_threads",
        "model",
        existing_type=sa.String(length=100),
        server_default="default",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore legacy DB-level default."""
    op.alter_column(
        "chat_threads",
        "model",
        existing_type=sa.String(length=100),
        server_default="gpt-4o",
        existing_nullable=False,
    )

