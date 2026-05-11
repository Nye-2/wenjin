"""capability skill closed loop

Revision ID: 043_capability_skill_closed_loop
Revises: 042_archive_legacy_tables
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "043_capability_skill_closed_loop"
down_revision: str | None = "042_archive_legacy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 1. Drop capability_active_versions (no version concept anymore)
    if _has_table("capability_active_versions"):
        op.drop_table("capability_active_versions")

    # 2. Simplify capabilities: drop version, created_at, updated_at, system_prompt
    #    Recreate the table with new PK (id, workspace_type)
    op.execute("DROP TABLE IF EXISTS capabilities CASCADE")
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("workspace_type", sa.String(length=50), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("intent_description", sa.Text(), nullable=False),
        sa.Column("trigger_phrases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("required_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("brief_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("graph_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_card_template", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_capabilities_active",
        "capabilities",
        ["workspace_type", "enabled"],
        postgresql_where=sa.text("enabled = true"),
    )

    # 3. Create capability_skills (flat, global)
    op.create_table(
        "capability_skills",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("subagent_type", sa.String(length=50), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("allowed_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("resources", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("capability_skills")
    op.drop_table("capabilities")
