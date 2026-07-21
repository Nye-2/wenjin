"""Remove the unused workspace discipline field.

Revision ID: 108_remove_workspace_discipline
Revises: 107_runtime_accounting
"""

from alembic import op

revision = "108_remove_workspace_discipline"
down_revision = "107_runtime_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspaces", "discipline")


def downgrade() -> None:
    raise RuntimeError(
        "108 is an irreversible field-removal cutover; restore from backup if needed"
    )
