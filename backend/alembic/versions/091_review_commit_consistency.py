"""add review policy projection and commit attempt fencing

Revision ID: 091_review_commit_consistency
Revises: 090_auxiliary_task_cleanup
"""

import sqlalchemy as sa

from alembic import op

revision = "091_review_commit_consistency"
down_revision = "090_auxiliary_task_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in (
        "requires_explicit_review",
        "batch_acceptable",
        "suggested_selected",
    ):
        op.add_column(
            "mission_review_items",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.add_column("mission_commits", sa.Column("attempt_token", sa.String(160)))
    op.add_column("mission_commits", sa.Column("attempt_started_at", sa.DateTime(timezone=True)))
    op.add_column("mission_commits", sa.Column("attempt_expires_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_mission_commits_applying_expiry",
        "mission_commits",
        ["attempt_expires_at"],
        postgresql_where=sa.text("status = 'applying'"),
    )
    op.create_index(
        "uq_workspace_memory_revisions_mission_commit",
        "workspace_memory_revisions",
        ["source_mission_commit_id"],
        unique=True,
        postgresql_where=sa.text("source_mission_commit_id IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("091 is an irreversible development cutover; reseed instead")
