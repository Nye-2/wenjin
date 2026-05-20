"""Add DataService room review trace hooks.

Revision ID: 069_dataservice_rooms_hooks
Revises: 068_dataservice_sandbox_runtime
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "069_dataservice_rooms_hooks"
down_revision: str | None = "068_dataservice_sandbox_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROOM_TABLES = ("decisions", "memory_facts", "workspace_tasks")


def upgrade() -> None:
    op.alter_column("decisions", "extracted_by", existing_type=sa.String(length=20), type_=sa.String(length=100))
    for table_name in ROOM_TABLES:
        op.add_column(table_name, sa.Column("source_review_batch_id", sa.String(length=36), nullable=True))
        op.add_column(table_name, sa.Column("source_review_item_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_source_review_batch_id",
            table_name,
            "review_batches",
            ["source_review_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table_name}_source_review_item_id",
            table_name,
            "review_items",
            ["source_review_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table_name}_source_review_item", table_name, ["source_review_item_id"])


def downgrade() -> None:
    for table_name in reversed(ROOM_TABLES):
        op.drop_index(f"ix_{table_name}_source_review_item", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_source_review_item_id", table_name, type_="foreignkey")
        op.drop_constraint(f"fk_{table_name}_source_review_batch_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "source_review_item_id")
        op.drop_column(table_name, "source_review_batch_id")
    op.alter_column("decisions", "extracted_by", existing_type=sa.String(length=100), type_=sa.String(length=20))
