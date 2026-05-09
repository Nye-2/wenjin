"""Create decisions table.

Revision ID: 035_create_decisions
Revises: 034_create_documents_v2
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "035_create_decisions"
down_revision = "034_create_documents_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("confidence", sa.REAL, nullable=False, server_default="1.0"),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("extracted_by", sa.String(20), nullable=False),
        sa.Column(
            "superseded_by",
            sa.String(36),
            sa.ForeignKey("decisions.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_decisions_active",
        "decisions",
        ["workspace_id", "key"],
        postgresql_where=sa.text("deleted_at IS NULL AND superseded_by IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_decisions_active", table_name="decisions")
    op.drop_table("decisions")
