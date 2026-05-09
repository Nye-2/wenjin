"""Create memory_facts table.

Revision ID: 036_create_memory_facts
Revises: 035_create_decisions
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "036_create_memory_facts"
down_revision = "035_create_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("confidence", sa.REAL, nullable=False, server_default="1.0"),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memory_ws_cat",
        "memory_facts",
        ["workspace_id", "category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memory_ws_cat", table_name="memory_facts")
    op.drop_table("memory_facts")
