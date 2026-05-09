"""Archive legacy tables replaced by v2

Revision ID: 042_archive_legacy_tables
Revises: 041_create_capabilities
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "042_archive_legacy_tables"
down_revision = "041_create_capabilities"
branch_labels = None
depends_on = None

LEGACY_RENAMES = [
    ("workspace_references", "_legacy_workspace_references"),
]


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    for old_name, new_name in LEGACY_RENAMES:
        if _has_table(old_name):
            op.rename_table(old_name, new_name)


def downgrade() -> None:
    for old_name, new_name in reversed(LEGACY_RENAMES):
        if _has_table(new_name):
            op.rename_table(new_name, old_name)
