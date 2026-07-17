"""Require Mission budgets and make chat-turn billing atomic.

Revision ID: 107_runtime_accounting
Revises: 106_remove_sandbox_pricing_policy
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "107_runtime_accounting"
down_revision = "106_remove_sandbox_pricing_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("107_runtime_accounting targets PostgreSQL only")
    has_development_data = bool(
        conn.execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM users LIMIT 1"
                ") OR EXISTS ("
                "SELECT 1 FROM mission_runs LIMIT 1"
                ") OR EXISTS ("
                "SELECT 1 FROM credit_transactions LIMIT 1"
                ") OR EXISTS ("
                "SELECT 1 FROM pricing_policies LIMIT 1"
                ")"
            )
        ).scalar()
    )
    if has_development_data:
        raise RuntimeError(
            "107 is a development drop/reseed cutover; existing users, pricing, "
            "Mission, or credit history cannot be migrated without violating "
            "cumulative accounting"
        )

    op.add_column(
        "users",
        sa.Column(
            "thread_consumed_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "reserved_thread_free_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_users_thread_token_counters_nonnegative",
        "users",
        "thread_consumed_tokens >= 0 AND reserved_thread_free_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_users_credit_counters_nonnegative",
        "users",
        "reserved_credits >= 0 AND total_credits_earned >= 0 "
        "AND total_credits_spent >= 0",
    )

    op.add_column(
        "credit_transactions",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.create_index(
        "uq_credit_transactions_user_type_idempotency",
        "credit_transactions",
        ["user_id", "transaction_type", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "thread_turn_billings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("user_message_id", sa.String(length=36), nullable=True),
        sa.Column("assistant_message_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="authorized",
        ),
        sa.Column("reserved_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_free_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("settled_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "pricing_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('authorized', 'settled', 'released', 'expired')",
            name="ck_thread_turn_billings_status",
        ),
        sa.CheckConstraint(
            "reserved_credits >= 0 AND settled_credits >= 0 "
            "AND reserved_free_tokens >= 0 "
            "AND settled_credits <= reserved_credits",
            name="ck_thread_turn_billings_nonnegative_money",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND cached_input_tokens >= 0 "
            "AND output_tokens >= 0 AND reasoning_tokens >= 0 "
            "AND total_tokens >= 0 "
            "AND cached_input_tokens <= input_tokens "
            "AND reasoning_tokens <= output_tokens "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_thread_turn_billings_nonnegative_usage",
        ),
        sa.CheckConstraint(
            "(status = 'authorized' AND settled_at IS NULL AND released_at IS NULL) "
            "OR (status = 'settled' AND settled_at IS NOT NULL AND released_at IS NULL) "
            "OR (status IN ('released', 'expired') AND settled_at IS NULL "
            "AND released_at IS NOT NULL)",
            name="ck_thread_turn_billings_state_timestamps",
        ),
        sa.CheckConstraint(
            "(status = 'settled' AND total_tokens > 0) "
            "OR (status <> 'settled' AND input_tokens = 0 "
            "AND cached_input_tokens = 0 AND output_tokens = 0 "
            "AND reasoning_tokens = 0 AND total_tokens = 0)",
            name="ck_thread_turn_billings_usage_state",
        ),
        sa.CheckConstraint(
            "(status = 'settled' AND transaction_id IS NOT NULL) "
            "OR (status <> 'settled' AND transaction_id IS NULL)",
            name="ck_thread_turn_billings_transaction_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_message_id"], ["thread_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["thread_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transaction_id"], ["credit_transactions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_message_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("transaction_id"),
        sa.UniqueConstraint("user_message_id"),
    )
    op.create_index(
        "ix_thread_turn_billings_user_id",
        "thread_turn_billings",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_turn_billings_thread_id",
        "thread_turn_billings",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_turn_billings_workspace_id",
        "thread_turn_billings",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_turn_billings_authorized_expiry",
        "thread_turn_billings",
        ["expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'authorized'"),
    )
    op.alter_column("mission_runs", "mission_policy_id", nullable=False)


def downgrade() -> None:
    raise RuntimeError("107 is an irreversible development cutover; reseed instead")
