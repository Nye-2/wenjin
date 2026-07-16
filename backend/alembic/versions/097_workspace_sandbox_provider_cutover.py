"""remove obsolete configurable sandbox provider

Revision ID: 097_workspace_sandbox_provider_cutover
Revises: 096_mission_aggregate_references
"""

from alembic import op

revision = "097_workspace_sandbox_provider_cutover"
down_revision = "096_mission_aggregate_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspace_settings", "sandbox_provider")


def downgrade() -> None:
    raise RuntimeError("097 is an irreversible development cutover; reseed instead")
