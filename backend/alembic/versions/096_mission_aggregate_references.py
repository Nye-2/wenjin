"""enforce Mission aggregate cross-row ownership

Revision ID: 096_mission_aggregate_references
Revises: 095_database_physical_integrity
"""

from alembic import op

revision = "096_mission_aggregate_references"
down_revision = "095_database_physical_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_mission_review_items_mission_item",
        "mission_review_items",
        ["mission_id", "review_item_id"],
    )
    op.create_foreign_key(
        "fk_mission_review_items_source_item",
        "mission_review_items",
        "mission_items",
        ["mission_id", "source_item_seq"],
        ["mission_id", "seq"],
    )
    op.drop_constraint(
        "mission_commits_mission_id_fkey",
        "mission_commits",
        type_="foreignkey",
    )
    op.drop_constraint(
        "mission_commits_review_item_id_fkey",
        "mission_commits",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_mission_commits_review_item",
        "mission_commits",
        "mission_review_items",
        ["mission_id", "review_item_id"],
        ["mission_id", "review_item_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise RuntimeError("096 is an irreversible development cutover; reseed instead")
