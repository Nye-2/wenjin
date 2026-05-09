"""Create documents_v2 table.

Revision ID: 034_create_documents_v2
Revises: 033_create_library_items
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "034_create_documents_v2"
down_revision = "033_create_library_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents_v2",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("documents_v2.id"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("added_by", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_documents_v2_ws_active",
        "documents_v2",
        ["workspace_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_v2_ws_active", table_name="documents_v2")
    op.drop_table("documents_v2")
