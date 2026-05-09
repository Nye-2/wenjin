"""Create workspace_settings table.

Revision ID: 032_create_workspace_settings
Revises: 031_add_workspace_thread_link
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "032_create_workspace_settings"
down_revision = "031_add_workspace_thread_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_settings",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("default_model", sa.String(100), nullable=True),
        sa.Column(
            "thinking_enabled",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "sandbox_provider",
            sa.String(50),
            nullable=False,
            server_default="local",
        ),
        sa.Column(
            "auto_compact_threshold",
            sa.REAL,
            nullable=False,
            server_default="0.8",
        ),
        sa.Column(
            "capability_overrides",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_settings")
