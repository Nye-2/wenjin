"""derive review policy at projection time and fence Mission assets by source

Revision ID: 102_review_policy_projection_cutover
Revises: 101_workspace_reasoning_effort_cutover
"""

import sqlalchemy as sa

from alembic import op

revision = "102_review_policy_projection_cutover"
down_revision = "101_workspace_reasoning_effort_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("mission_review_items", "suggested_selected")
    op.drop_column("mission_review_items", "batch_acceptable")
    op.drop_column("mission_review_items", "requires_explicit_review")
    op.create_index(
        "uq_workspace_assets_mission_review_source",
        "workspace_assets",
        ["workspace_id", "source_kind", "source_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_kind = 'mission_review_item' AND source_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source_kind = 'mission_review_item' AND source_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    raise RuntimeError("102 is an irreversible development cutover; reseed instead")
