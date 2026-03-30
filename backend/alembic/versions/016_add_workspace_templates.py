"""Add workspace_templates table.

Revision ID: 016_add_workspace_templates
Revises: 015_drop_paper_chunk_embedding
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "016_add_workspace_templates"
down_revision: Union[str, None] = "015_drop_paper_chunk_embedding"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _table_names() -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def upgrade() -> None:
    if "workspace_templates" in _table_names():
        return

    op.create_table(
        "workspace_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="thesis"),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="text"),
        sa.Column("source_file_path", sa.Text, nullable=True),
        sa.Column("structure", JSONB, nullable=True),
        sa.Column("format_spec", JSONB, nullable=True),
        sa.Column("content_guidelines", JSONB, nullable=True),
        sa.Column("latex_preamble", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_workspace_templates_workspace_id", "workspace_templates", ["workspace_id"])


def downgrade() -> None:
    if "workspace_templates" in _table_names():
        op.drop_index("ix_workspace_templates_workspace_id")
        op.drop_table("workspace_templates")
