"""replace capability catalogs with Mission policy catalogs

Revision ID: 089_mission_policy_catalog
Revises: 088_mission_linked_domains
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "089_mission_policy_catalog"
down_revision = "088_mission_linked_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_policies",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("workspace_type", sa.String(50), primary_key=True),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("policy_json", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
    )
    op.create_index("ix_mission_policies_enabled_workspace", "mission_policies", ["workspace_type", "enabled"])
    op.create_table(
        "worker_skills",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("skill_json", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
    )
    op.drop_table("agent_templates")
    op.drop_table("capability_skills")
    op.drop_table("capabilities")
    op.drop_table("capability_seed_revisions")
    op.drop_table("capability_definitions")


def downgrade() -> None:
    raise RuntimeError("089 is an irreversible development cutover; reseed instead")
