"""Add DataService capability catalog tables.

Revision ID: 062_dataservice_capability_catalog
Revises: 061_dataservice_conversation_blocks
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "062_dataservice_capability_catalog"
down_revision: str | None = "061_dataservice_conversation_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "capability_definitions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("workspace_type", sa.String(length=50), nullable=False),
        sa.Column("schema_version", sa.String(length=50), server_default="capability.v2", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("tier", sa.String(length=50), server_default="primary", nullable=False),
        sa.Column("entry_surface", sa.String(length=50), server_default="workbench", nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("intent_description", sa.Text(), server_default="", nullable=False),
        sa.Column("trigger_phrases", _json_type(), server_default="[]", nullable=False),
        sa.Column("required_decisions", _json_type(), server_default="[]", nullable=False),
        sa.Column("brief_schema", _json_type(), server_default="{}", nullable=False),
        sa.Column("graph_template", _json_type(), server_default="{}", nullable=False),
        sa.Column("ui_meta", _json_type(), server_default="{}", nullable=False),
        sa.Column("runtime", _json_type(), server_default="{}", nullable=False),
        sa.Column("dashboard_meta", _json_type(), server_default="{}", nullable=False),
        sa.Column("definition_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", "workspace_type"),
    )
    op.create_index(
        "ix_capability_definitions_active",
        "capability_definitions",
        ["workspace_type", "enabled"],
        postgresql_where=sa.text("enabled = true"),
    )

    op.create_table(
        "capability_seed_revisions",
        sa.Column("catalog_kind", sa.String(length=50), nullable=False),
        sa.Column("seed_root", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("loaded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_capability_seed_revisions_kind_root",
        "capability_seed_revisions",
        ["catalog_kind", "seed_root"],
    )

    with op.batch_alter_table("capability_skills") as batch_op:
        batch_op.add_column(sa.Column("schema_version", sa.String(length=50), server_default="capability_skill.v2", nullable=False))
        batch_op.add_column(sa.Column("worker_type", sa.String(length=50), server_default="react", nullable=False))
        batch_op.add_column(sa.Column("skill_json", _json_type(), server_default="{}", nullable=False))
        batch_op.add_column(sa.Column("checksum", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_path", sa.Text(), nullable=True))

    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "postgresql":
        conn.execute(sa.text("""
            INSERT INTO capability_definitions (
                id, workspace_type, schema_version, enabled, tier, entry_surface,
                display_name, description, intent_description, trigger_phrases,
                required_decisions, brief_schema, graph_template, ui_meta, runtime,
                dashboard_meta, definition_json, notes, created_at, updated_at
            )
            SELECT
                id, workspace_type, 'capability.v2', enabled, 'primary', 'workbench',
                display_name, description, intent_description, trigger_phrases,
                required_decisions, brief_schema, graph_template, ui_meta, runtime,
                dashboard_meta,
                jsonb_build_object(
                    'schema_version', 'capability.v2',
                    'id', id,
                    'workspace_type', workspace_type,
                    'enabled', enabled,
                    'display_name', display_name,
                    'description', description,
                    'intent_description', intent_description,
                    'trigger_phrases', trigger_phrases,
                    'required_decisions', required_decisions,
                    'brief_schema', brief_schema,
                    'graph_template', graph_template,
                    'ui_meta', ui_meta,
                    'runtime', runtime,
                    'dashboard_meta', dashboard_meta,
                    'notes', notes
                ),
                notes, now(), now()
            FROM capabilities
            ON CONFLICT (id, workspace_type) DO NOTHING
        """))
        conn.execute(sa.text("""
            UPDATE capability_skills
            SET worker_type = subagent_type,
                skill_json = jsonb_build_object(
                    'schema_version', 'capability_skill.v2',
                    'id', id,
                    'enabled', enabled,
                    'display_name', display_name,
                    'description', description,
                    'worker_type', subagent_type,
                    'subagent_type', subagent_type,
                    'prompt', prompt,
                    'allowed_tools', allowed_tools,
                    'resources', resources,
                    'config', config
                )
        """))


def downgrade() -> None:
    with op.batch_alter_table("capability_skills") as batch_op:
        batch_op.drop_column("source_path")
        batch_op.drop_column("checksum")
        batch_op.drop_column("skill_json")
        batch_op.drop_column("worker_type")
        batch_op.drop_column("schema_version")
    op.drop_index("ix_capability_seed_revisions_kind_root", table_name="capability_seed_revisions")
    op.drop_table("capability_seed_revisions")
    op.drop_index("ix_capability_definitions_active", table_name="capability_definitions")
    op.drop_table("capability_definitions")
