"""agent_templates

Revision ID: 076_agent_templates
Revises: 075_enforce_workspace_owner_membership
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "076_agent_templates"
down_revision: str | None = "075_enforce_workspace_owner_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=50), server_default="agent_template.v1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_role", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("persona_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("default_skills", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("tool_affinity", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("risk_profile", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("output_contracts", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("quality_expectations", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("runtime_defaults", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("template_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_templates_enabled_category",
        "agent_templates",
        ["enabled", "category"],
        postgresql_where=sa.text("enabled = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_templates_enabled_category", table_name="agent_templates")
    op.drop_table("agent_templates")
