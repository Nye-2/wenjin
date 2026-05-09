"""Create capabilities tables.

Revision ID: 041_create_capabilities
Revises: 040_create_audit_logs
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision = "041_create_capabilities"
down_revision = "040_create_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("workspace_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("intent_description", sa.Text, nullable=False),
        sa.Column("trigger_phrases", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("required_decisions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("brief_schema", JSONB, nullable=False),
        sa.Column("graph_template", JSONB, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("result_card_template", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", "workspace_type", "version"),
    )
    op.create_index(
        "ix_capabilities_active",
        "capabilities",
        ["workspace_type", "enabled"],
        postgresql_where=sa.text("enabled = true"),
    )
    op.create_table(
        "capability_active_versions",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("workspace_type", sa.String(50), nullable=False),
        sa.Column("active_version", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("id", "workspace_type"),
    )
    op.create_foreign_key(
        "fk_capability_active_version_capability",
        "capability_active_versions",
        "capabilities",
        ["id", "workspace_type", "active_version"],
        ["id", "workspace_type", "version"],
    )


def downgrade() -> None:
    op.drop_table("capability_active_versions")
    op.drop_index("ix_capabilities_active", table_name="capabilities")
    op.drop_table("capabilities")
