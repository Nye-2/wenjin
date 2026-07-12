"""cut billing attribution and pricing over to Mission semantics

Revision ID: 093_mission_billing_cutover
Revises: 092_mission_runtime_reliability
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "093_mission_billing_cutover"
down_revision = "092_mission_runtime_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "credit_transactions",
        "feature_id",
        new_column_name="mission_policy_id",
        existing_type=sa.String(100),
        type_=sa.String(120),
    )
    op.execute("UPDATE credit_transactions SET mission_policy_id = NULL")
    op.add_column(
        "credit_transactions",
        sa.Column("mission_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "credit_transactions",
        sa.Column("operation_key", sa.String(200), nullable=True),
    )
    op.create_foreign_key(
        "fk_credit_transactions_mission",
        "credit_transactions",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_credit_transactions_mission_id",
        "credit_transactions",
        ["mission_id"],
    )

    op.execute("DELETE FROM pricing_policies WHERE policy_kind::text = 'capability'")
    op.execute("ALTER TABLE pricing_policies ALTER COLUMN policy_kind TYPE text USING policy_kind::text")
    op.execute("DROP TYPE pricing_policy_kind")
    pricing_kind = postgresql.ENUM(
        "global_credit",
        "model_usage",
        "mission",
        "tool",
        "sandbox",
        name="pricing_policy_kind",
    )
    pricing_kind.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE pricing_policies ALTER COLUMN policy_kind "
        "TYPE pricing_policy_kind USING policy_kind::pricing_policy_kind"
    )


def downgrade() -> None:
    raise RuntimeError("093 is an irreversible development cutover; reseed instead")
