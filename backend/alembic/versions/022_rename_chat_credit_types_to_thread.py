"""rename chat credit transaction semantics to thread

Revision ID: 022_rename_chat_credit_types_to_thread
Revises: 021_subagent_exec_fk
Create Date: 2026-04-14
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_rename_chat_credit_types_to_thread"
down_revision: str | None = "021_subagent_exec_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate chat token credit semantics to thread naming."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'credit_transaction_type'
                  AND e.enumlabel = 'chat_token_consume'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'credit_transaction_type'
                  AND e.enumlabel = 'thread_token_consume'
            ) THEN
                ALTER TYPE credit_transaction_type
                RENAME VALUE 'chat_token_consume' TO 'thread_token_consume';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET transaction_type = 'thread_token_consume'
        WHERE transaction_type::text = 'chat_token_consume';
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET feature_id = 'thread'
        WHERE feature_id = 'chat'
          AND transaction_type::text IN ('chat_token_consume', 'thread_token_consume');
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET metadata = jsonb_set(
            metadata::jsonb,
            '{type}',
            '"thread_token_billing"'::jsonb,
            true
        )
        WHERE metadata::jsonb ->> 'type' = 'chat_token_billing';
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET metadata = jsonb_set(
            metadata::jsonb,
            '{original_transaction_type}',
            '"thread_token_consume"'::jsonb,
            true
        )
        WHERE metadata::jsonb ->> 'original_transaction_type' = 'chat_token_consume';
        """
    )


def downgrade() -> None:
    """Revert thread token credit semantics back to chat naming."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'credit_transaction_type'
                  AND e.enumlabel = 'thread_token_consume'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'credit_transaction_type'
                  AND e.enumlabel = 'chat_token_consume'
            ) THEN
                ALTER TYPE credit_transaction_type
                RENAME VALUE 'thread_token_consume' TO 'chat_token_consume';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET transaction_type = 'chat_token_consume'
        WHERE transaction_type::text = 'thread_token_consume';
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET feature_id = 'chat'
        WHERE feature_id = 'thread'
          AND transaction_type::text IN ('chat_token_consume', 'thread_token_consume');
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET metadata = jsonb_set(
            metadata::jsonb,
            '{type}',
            '"chat_token_billing"'::jsonb,
            true
        )
        WHERE metadata::jsonb ->> 'type' = 'thread_token_billing';
        """
    )

    op.execute(
        """
        UPDATE credit_transactions
        SET metadata = jsonb_set(
            metadata::jsonb,
            '{original_transaction_type}',
            '"chat_token_consume"'::jsonb,
            true
        )
        WHERE metadata::jsonb ->> 'original_transaction_type' = 'thread_token_consume';
        """
    )
