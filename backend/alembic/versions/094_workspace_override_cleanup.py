"""remove workspace-level product capability overrides

Revision ID: 094_workspace_override_cleanup
Revises: 093_mission_billing_cutover
"""

from __future__ import annotations

from alembic import op

revision = "094_workspace_override_cleanup"
down_revision = "093_mission_billing_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspace_settings", "capability_overrides")


def downgrade() -> None:
    raise RuntimeError("094 is an irreversible development cutover; reseed instead")
