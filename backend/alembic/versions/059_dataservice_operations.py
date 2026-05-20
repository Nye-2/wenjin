"""create DataService operational metadata tables

Revision ID: 059_dataservice_operations
Revises: 058_prism_canonical_review_tables
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "059_dataservice_operations"
down_revision: str | None = "058_prism_canonical_review_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataservice_idempotency_keys",
        sa.Column("source_service", sa.String(length=80), nullable=False),
        sa.Column("command_name", sa.String(length=120), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_hash", "idempotency_key", name="uq_dataservice_idempotency_scope_key"),
    )
    op.create_index("ix_dataservice_idempotency_actor", "dataservice_idempotency_keys", ["actor_user_id"], unique=False)
    op.create_index("ix_dataservice_idempotency_status", "dataservice_idempotency_keys", ["status"], unique=False)
    op.create_index("ix_dataservice_idempotency_workspace", "dataservice_idempotency_keys", ["workspace_id"], unique=False)

    op.create_table(
        "dataservice_outbox_events",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("aggregate_kind", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataservice_outbox_aggregate", "dataservice_outbox_events", ["aggregate_kind", "aggregate_id"], unique=False)
    op.create_index("ix_dataservice_outbox_status_created", "dataservice_outbox_events", ["status", "created_at"], unique=False)
    op.create_index("ix_dataservice_outbox_workspace", "dataservice_outbox_events", ["workspace_id"], unique=False)

    op.create_table(
        "dataservice_migration_reports",
        sa.Column("migration_key", sa.String(length=120), nullable=False),
        sa.Column("source_module", sa.String(length=255), nullable=False),
        sa.Column("target_domain", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="planned", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("migration_key", name="uq_dataservice_migration_reports_key"),
    )
    op.create_index("ix_dataservice_migration_reports_status", "dataservice_migration_reports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dataservice_migration_reports_status", table_name="dataservice_migration_reports")
    op.drop_table("dataservice_migration_reports")
    op.drop_index("ix_dataservice_outbox_workspace", table_name="dataservice_outbox_events")
    op.drop_index("ix_dataservice_outbox_status_created", table_name="dataservice_outbox_events")
    op.drop_index("ix_dataservice_outbox_aggregate", table_name="dataservice_outbox_events")
    op.drop_table("dataservice_outbox_events")
    op.drop_index("ix_dataservice_idempotency_workspace", table_name="dataservice_idempotency_keys")
    op.drop_index("ix_dataservice_idempotency_status", table_name="dataservice_idempotency_keys")
    op.drop_index("ix_dataservice_idempotency_actor", table_name="dataservice_idempotency_keys")
    op.drop_table("dataservice_idempotency_keys")
