"""Create library_items table.

Revision ID: 033_create_library_items
Revises: 032_create_workspace_settings
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "033_create_library_items"
down_revision = "032_create_workspace_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "library_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("venue", sa.String(200), nullable=True),
        sa.Column("doi", sa.String(200), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("full_text_path", sa.String(500), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cited_in_documents", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("added_by", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_library_workspace_active",
        "library_items",
        ["workspace_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_library_workspace_active", table_name="library_items")
    op.drop_table("library_items")
