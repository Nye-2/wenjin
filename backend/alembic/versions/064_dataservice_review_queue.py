"""Add DataService review batch aggregate.

Revision ID: 064_dataservice_review_queue
Revises: 063_dataservice_execution_graph
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "064_dataservice_review_queue"
down_revision: str | None = "063_dataservice_execution_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "review_batches",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("review_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(length=50), server_default="review_batch.v1", nullable=False),
        sa.Column("item_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_batches_workspace_status", "review_batches", ["workspace_id", "status"])
    op.create_index("ix_review_batches_execution", "review_batches", ["execution_id"])

    op.create_table(
        "review_items",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_item_id", sa.String(length=255), nullable=True),
        sa.Column("item_kind", sa.String(length=64), nullable=False),
        sa.Column("target_domain", sa.String(length=64), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_ref_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("preview_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("result_json", _json_type(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("provenance_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["review_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_items_batch_status", "review_items", ["batch_id", "status"])
    op.create_index("ix_review_items_workspace_status", "review_items", ["workspace_id", "status"])
    op.create_index("ix_review_items_target", "review_items", ["target_domain", "target_kind"])

    op.create_table(
        "review_action_logs",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("status_from", sa.String(length=32), nullable=True),
        sa.Column("status_to", sa.String(length=32), nullable=True),
        sa.Column("payload_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["review_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["review_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_action_logs_batch_created", "review_action_logs", ["batch_id", "created_at"])
    op.create_index("ix_review_action_logs_item_created", "review_action_logs", ["item_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_action_logs_item_created", table_name="review_action_logs")
    op.drop_index("ix_review_action_logs_batch_created", table_name="review_action_logs")
    op.drop_table("review_action_logs")
    op.drop_index("ix_review_items_target", table_name="review_items")
    op.drop_index("ix_review_items_workspace_status", table_name="review_items")
    op.drop_index("ix_review_items_batch_status", table_name="review_items")
    op.drop_table("review_items")
    op.drop_index("ix_review_batches_execution", table_name="review_batches")
    op.drop_index("ix_review_batches_workspace_status", table_name="review_batches")
    op.drop_table("review_batches")
