"""add chat token consume credit transaction type

Revision ID: 013_add_chat_token_consume_type
Revises: 012_add_subagent_task_records
Create Date: 2026-03-26
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_add_chat_token_consume_type"
down_revision: str | None = "012_add_subagent_task_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the chat token billing enum value for credit transactions."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE credit_transaction_type "
            "ADD VALUE IF NOT EXISTS 'chat_token_consume'"
        )


def downgrade() -> None:
    """Downgrade is a no-op because PostgreSQL enum value removal is destructive."""
    pass
