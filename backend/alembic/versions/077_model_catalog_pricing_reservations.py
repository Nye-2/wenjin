"""model catalog pricing reservations

Revision ID: 077_model_catalog_pricing_reservations
Revises: 076_agent_templates
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "077_model_catalog_pricing_reservations"
down_revision: str | None = "076_agent_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reserved_credits", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "pricing_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("policy_key", sa.String(length=120), nullable=False),
        sa.Column(
            "policy_kind",
            sa.Enum(
                "global_credit",
                "model_usage",
                "capability",
                "tool",
                "sandbox",
                name="pricing_policy_kind",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("config_json", _jsonb(), server_default="{}", nullable=False),
        sa.Column("created_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_key", name="uq_pricing_policy_key"),
    )
    op.create_index("ix_pricing_policies_policy_key", "pricing_policies", ["policy_key"])
    op.create_index("ix_pricing_policies_policy_kind", "pricing_policies", ["policy_kind"])
    op.create_index(
        "ix_pricing_policies_kind_enabled",
        "pricing_policies",
        ["policy_kind", "enabled"],
    )

    op.create_table(
        "model_catalog_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column(
            "provider_protocol",
            sa.Enum("openai_compatible", name="model_provider_protocol"),
            server_default="openai_compatible",
            nullable=False,
        ),
        sa.Column("provider_name", sa.String(length=100), server_default="Custom", nullable=False),
        sa.Column(
            "category",
            sa.Enum("llm", "image", name="model_category"),
            server_default="llm",
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("api_key_last4", sa.String(length=16), nullable=True),
        sa.Column("api_key_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("supports_tools", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("supports_json_mode", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("supports_json_schema", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("supports_vision", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("supports_reasoning_effort", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="4096", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=True),
        sa.Column("max_retries", sa.Integer(), nullable=True),
        sa.Column(
            "trust_level",
            sa.Enum("trusted", "custom", name="model_trust_level"),
            server_default="custom",
            nullable=False,
        ),
        sa.Column("pricing_policy_id", sa.String(length=36), nullable=True),
        sa.Column("config_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "health_status",
            sa.Enum("unknown", "healthy", "failed", name="model_health_status"),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("default_headers", _jsonb(), server_default="{}", nullable=False),
        sa.Column("created_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", name="uq_model_catalog_model_id"),
    )
    op.create_index("ix_model_catalog_entries_model_id", "model_catalog_entries", ["model_id"])
    op.create_index(
        "ix_model_catalog_entries_api_key_fingerprint",
        "model_catalog_entries",
        ["api_key_fingerprint"],
    )
    op.create_index("ix_model_catalog_entries_pricing_policy_id", "model_catalog_entries", ["pricing_policy_id"])
    op.create_index("ix_model_catalog_health_status", "model_catalog_entries", ["health_status"])
    op.create_index("ix_model_catalog_enabled_category", "model_catalog_entries", ["enabled", "category"])
    op.create_index("ix_model_catalog_default_category", "model_catalog_entries", ["is_default", "category"])
    op.create_index(
        "uq_model_catalog_enabled_default_category",
        "model_catalog_entries",
        ["category"],
        unique=True,
        postgresql_where=sa.text("enabled = true AND is_default = true"),
    )

    op.create_table(
        "credit_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("execution_id", sa.String(length=100), nullable=True),
        sa.Column("node_id", sa.String(length=200), nullable=True),
        sa.Column(
            "scope",
            sa.Enum(
                "feature_execution",
                "sandbox_operation",
                "thread_turn",
                name="credit_reservation_scope",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "reserved",
                "settled",
                "released",
                "expired",
                name="credit_reservation_status",
            ),
            server_default="reserved",
            nullable=False,
        ),
        sa.Column("reserved_credits", sa.Integer(), nullable=False),
        sa.Column("settled_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", _jsonb(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_reservations_user_id", "credit_reservations", ["user_id"])
    op.create_index("ix_credit_reservations_workspace_id", "credit_reservations", ["workspace_id"])
    op.create_index("ix_credit_reservations_execution", "credit_reservations", ["execution_id"])
    op.create_index("ix_credit_reservations_transaction_id", "credit_reservations", ["transaction_id"])
    op.create_index("ix_credit_reservations_user_status", "credit_reservations", ["user_id", "status"])
    op.create_index(
        "ix_credit_reservations_idempotency",
        "credit_reservations",
        ["user_id", "scope", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_credit_reservations_idempotency", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_user_status", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_transaction_id", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_execution", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_workspace_id", table_name="credit_reservations")
    op.drop_index("ix_credit_reservations_user_id", table_name="credit_reservations")
    op.drop_table("credit_reservations")

    op.drop_index("uq_model_catalog_enabled_default_category", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_default_category", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_enabled_category", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_health_status", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_entries_pricing_policy_id", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_entries_api_key_fingerprint", table_name="model_catalog_entries")
    op.drop_index("ix_model_catalog_entries_model_id", table_name="model_catalog_entries")
    op.drop_table("model_catalog_entries")

    op.drop_index("ix_pricing_policies_kind_enabled", table_name="pricing_policies")
    op.drop_index("ix_pricing_policies_policy_kind", table_name="pricing_policies")
    op.drop_index("ix_pricing_policies_policy_key", table_name="pricing_policies")
    op.drop_table("pricing_policies")
    op.drop_column("users", "reserved_credits")
