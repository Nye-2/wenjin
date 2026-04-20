"""add task active dedupe partial index

Revision ID: 026_add_task_active_dedupe_index
Revises: 025_db_model_hardening
Create Date: 2026-04-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026_add_task_active_dedupe_index"
down_revision: str | None = "025_db_model_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in set(inspector.get_table_names())


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Create partial index for active task dedupe queries."""
    if not _has_index("task_records", "ix_task_records_active_dedupe_lookup"):
        op.create_index(
            "ix_task_records_active_dedupe_lookup",
            "task_records",
            [
                "user_id",
                "task_type",
                "workspace_id",
                "feature_id",
                "action",
                "created_at",
            ],
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )


def downgrade() -> None:
    """Drop active task dedupe partial index."""
    if _has_index("task_records", "ix_task_records_active_dedupe_lookup"):
        op.drop_index("ix_task_records_active_dedupe_lookup", table_name="task_records")
