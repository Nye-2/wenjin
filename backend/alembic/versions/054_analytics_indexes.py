"""Indexes for analytics aggregation queries.

Revision ID: 054_analytics_indexes
Revises: 053_capability_add_runtime_and_dashboard_meta
Create Date: 2026-05-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "054_analytics_indexes"
down_revision: str | None = "053_capability_add_runtime_and_dashboard_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Executions: composite index for workspace-type + time + status queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_workspace_type_created_status "
        "ON executions (workspace_type, created_at, status)"
    )
    # Users: index on created_at for growth queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_created_at "
        "ON users (created_at)"
    )
    # Credit ledger: composite index for user + time + type queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created_type "
        "ON credit_transactions (user_id, created_at, transaction_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_credit_ledger_user_created_type")
    op.execute("DROP INDEX IF EXISTS idx_users_created_at")
    op.execute("DROP INDEX IF EXISTS idx_executions_workspace_type_created_status")
