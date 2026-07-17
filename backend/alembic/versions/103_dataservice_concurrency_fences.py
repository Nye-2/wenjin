"""Fence concurrent decision and workspace-memory writes.

Revision ID: 103_dataservice_concurrency_fences
Revises: 102_review_policy_projection_cutover
"""

import sqlalchemy as sa

from alembic import op

revision = "103_dataservice_concurrency_fences"
down_revision = "102_review_policy_projection_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_decisions_active", table_name="decisions")
    op.create_index(
        "uq_decisions_active_workspace_key",
        "decisions",
        ["workspace_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND superseded_by IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND superseded_by IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("103 is an irreversible development cutover; reseed instead")
