"""workspace memory documents and dev memory cleanup

Revision ID: 082_workspace_memory_prism_migration
Revises: 081_latex_template_metadata
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "082_workspace_memory_prism_migration"
down_revision: str | None = "081_latex_template_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "workspace_memory_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.String(length=100), nullable=False),
        sa.Column("source_execution_id", sa.String(length=36), nullable=True),
        sa.Column("source_thread_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_workspace_memory_documents_workspace",
        "workspace_memory_documents",
        ["workspace_id"],
        unique=True,
    )
    op.create_table(
        "workspace_memory_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("workspace_memory_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("update_reason", sa.String(length=100), nullable=False),
        sa.Column("source_execution_id", sa.String(length=36), nullable=True),
        sa.Column("source_thread_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_workspace_memory_revisions_document_revision",
        "workspace_memory_revisions",
        ["document_id", "revision"],
        unique=True,
    )
    op.create_index(
        "ix_workspace_memory_revisions_workspace_revision",
        "workspace_memory_revisions",
        ["workspace_id", "revision"],
        unique=False,
    )

    op.drop_table("memory_facts")
    op.drop_index("ix_user_knowledge_confidence", table_name="user_knowledge")
    op.drop_index("ix_user_knowledge_user_category", table_name="user_knowledge")
    op.drop_table("user_knowledge")


def downgrade() -> None:
    op.create_table(
        "user_knowledge",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("workspace_context", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_knowledge_user_category", "user_knowledge", ["user_id", "category"])
    op.create_index("ix_user_knowledge_confidence", "user_knowledge", ["confidence"])
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("source_review_batch_id", sa.String(length=36), nullable=True),
        sa.Column("source_review_item_id", sa.String(length=36), nullable=True),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_ws_cat", "memory_facts", ["workspace_id", "category"])
    op.drop_index("ix_workspace_memory_revisions_workspace_revision", table_name="workspace_memory_revisions")
    op.drop_index("uq_workspace_memory_revisions_document_revision", table_name="workspace_memory_revisions")
    op.drop_table("workspace_memory_revisions")
    op.drop_index("uq_workspace_memory_documents_workspace", table_name="workspace_memory_documents")
    op.drop_table("workspace_memory_documents")
