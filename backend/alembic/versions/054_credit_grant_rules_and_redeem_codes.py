"""Credit grant rules + redeem codes + redemptions + referrals.

Revision ID: 054_credit_grant_rules_and_redeem_codes
Revises: 053_capability_add_runtime_and_dashboard_meta
Create Date: 2026-05-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "054_credit_grant_rules_and_redeem_codes"
down_revision: str | None = "053_capability_add_runtime_and_dashboard_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credit_transaction_type ADD VALUE IF NOT EXISTS 'referral_bonus'")
    op.execute("ALTER TYPE credit_transaction_type ADD VALUE IF NOT EXISTS 'redeem_code'")

    op.create_table(
        "credit_grant_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "rule_type",
            sa.Enum(
                "registration_bonus", "referral_referrer", "referral_referred", "periodic",
                name="credit_grant_rule_type",
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_admin_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_credit_grant_rules_type_enabled", "credit_grant_rules", ["rule_type", "enabled"])

    op.create_table(
        "credit_redeem_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_admin_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_redeem_codes_batch", "credit_redeem_codes", ["batch_id"])

    op.create_table(
        "credit_redemptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code_id", sa.String(36), sa.ForeignKey("credit_redeem_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("credit_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_redemption_code_user", "credit_redemptions", ["code_id", "user_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("referrer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referee_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("referrer_credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referee_credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referee_first_task_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("credit_redemptions")
    op.drop_index("idx_redeem_codes_batch", "credit_redeem_codes")
    op.drop_table("credit_redeem_codes")
    op.drop_index("idx_credit_grant_rules_type_enabled", "credit_grant_rules")
    op.drop_table("credit_grant_rules")
    op.execute("DROP TYPE IF EXISTS credit_grant_rule_type")
    # NOTE: PG cannot drop enum values; leave referral_bonus / redeem_code in place.
