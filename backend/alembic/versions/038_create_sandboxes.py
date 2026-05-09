"""Create sandboxes table.

Revision ID: 038_create_sandboxes
Revises: 037_create_run_history
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "038_create_sandboxes"
down_revision = "037_create_run_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sandboxes",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sandbox_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("workspace_path", sa.String(500), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sandboxes")
