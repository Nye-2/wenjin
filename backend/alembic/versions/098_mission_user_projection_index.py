"""index canonical user Mission projection

Revision ID: 098_mission_user_projection_index
Revises: 097_workspace_sandbox_provider_cutover
"""

from alembic import op

revision = "098_mission_user_projection_index"
down_revision = "097_workspace_sandbox_provider_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_mission_runs_user_updated_mission",
        "mission_runs",
        ["user_id", "updated_at", "mission_id"],
    )


def downgrade() -> None:
    raise RuntimeError("098 is an irreversible development cutover; reseed instead")
