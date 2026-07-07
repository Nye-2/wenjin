"""execution node unique upsert

Revision ID: 083_execution_node_unique_upsert
Revises: 082_workspace_memory_prism_migration
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "083_execution_node_unique_upsert"
down_revision: str | None = "082_workspace_memory_prism_migration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY execution_id, node_id
                    ORDER BY updated_at DESC, created_at DESC, id DESC
                ) AS row_num
            FROM execution_nodes
        )
        DELETE FROM execution_nodes
        WHERE id IN (
            SELECT id FROM ranked WHERE row_num > 1
        )
        """
    )
    op.drop_index("ix_execution_nodes_execution_node_id", table_name="execution_nodes")
    op.execute("DROP INDEX IF EXISTS ix_execution_nodes_execution_id")
    op.create_unique_constraint(
        "uq_execution_nodes_execution_node_id",
        "execution_nodes",
        ["execution_id", "node_id"],
    )
    op.create_index(
        "ix_execution_nodes_execution_id",
        "execution_nodes",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_execution_nodes_execution_id", table_name="execution_nodes")
    op.drop_constraint(
        "uq_execution_nodes_execution_node_id",
        "execution_nodes",
        type_="unique",
    )
    op.create_index(
        "ix_execution_nodes_execution_node_id",
        "execution_nodes",
        ["execution_id", "node_id"],
        unique=False,
    )
