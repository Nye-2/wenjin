"""Converge pricing and reservations on Mission-owned billing.

Revision ID: 106_remove_sandbox_pricing_policy
Revises: 105_remove_latex_compile_history
"""

from alembic import op

revision = "106_remove_sandbox_pricing_policy"
down_revision = "105_remove_latex_compile_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("106_remove_sandbox_pricing_policy targets PostgreSQL only")

    op.execute("DELETE FROM pricing_policies WHERE policy_kind = 'sandbox'")
    op.execute(
        "ALTER TABLE pricing_policies "
        "ALTER COLUMN policy_kind TYPE varchar(32) USING policy_kind::text"
    )
    op.execute("DROP TYPE pricing_policy_kind")
    op.execute(
        "CREATE TYPE pricing_policy_kind AS ENUM "
        "('global_credit', 'model_usage', 'mission', 'tool')"
    )
    op.execute(
        "ALTER TABLE pricing_policies ALTER COLUMN policy_kind "
        "TYPE pricing_policy_kind USING policy_kind::pricing_policy_kind"
    )

    op.execute("DELETE FROM credit_transactions WHERE transaction_type = 'refund'")
    op.execute(
        "ALTER TABLE credit_transactions ALTER COLUMN transaction_type "
        "TYPE varchar(32) USING transaction_type::text"
    )
    op.execute("DROP TYPE credit_transaction_type")
    op.execute(
        "CREATE TYPE credit_transaction_type AS ENUM "
        "('admin_grant', 'admin_deduct', 'workflow_consume', "
        "'thread_token_consume', 'registration_bonus', 'referral_bonus', "
        "'redeem_code')"
    )
    op.execute(
        "ALTER TABLE credit_transactions ALTER COLUMN transaction_type "
        "TYPE credit_transaction_type USING transaction_type::credit_transaction_type"
    )

    op.execute(
        "DELETE FROM credit_reservations "
        "WHERE scope <> 'mission' OR mission_id IS NULL"
    )
    op.execute(
        "DELETE FROM credit_reservations older USING credit_reservations newer "
        "WHERE older.mission_id = newer.mission_id "
        "AND (older.created_at, older.id) < (newer.created_at, newer.id)"
    )
    op.drop_index("ix_credit_reservations_idempotency", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_mission", table_name="credit_reservations")
    op.drop_constraint(
        "fk_credit_reservations_mission",
        "credit_reservations",
        type_="foreignkey",
    )
    op.drop_column("credit_reservations", "mission_item_seq")
    op.drop_column("credit_reservations", "scope")
    op.execute("DROP TYPE credit_reservation_scope")
    op.alter_column("credit_reservations", "mission_id", nullable=False)
    op.create_foreign_key(
        "fk_credit_reservations_mission",
        "credit_reservations",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_credit_reservations_mission",
        "credit_reservations",
        ["mission_id"],
        unique=True,
    )
    op.create_index(
        "ix_credit_reservations_idempotency",
        "credit_reservations",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError("106 is an irreversible development cutover; reseed instead")
