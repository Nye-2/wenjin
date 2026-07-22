"""Remove duplicate subagent projections from Mission snapshots.

Revision ID: 109_subagent_progress_ssot
Revises: 108_remove_workspace_discipline
"""

from alembic import op

revision = "109_subagent_progress_ssot"
down_revision = "108_remove_workspace_discipline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mission_runs
        SET snapshot_json = snapshot_json - 'subagent_summary' - 'team_summary'
        WHERE snapshot_json ? 'subagent_summary'
           OR snapshot_json ? 'team_summary'
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "109 is an irreversible Mission projection SSOT cutover; restore from backup if needed"
    )
