"""Make Mission evidence counters match unique semantic references.

Revision ID: 110_deduplicate_mission_references
Revises: 109_subagent_progress_ssot
"""

from alembic import op

revision = "110_deduplicate_mission_references"
down_revision = "109_subagent_progress_ssot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mission_runs AS mission
        SET evidence_count = (
            SELECT COUNT(
                DISTINCT COALESCE(
                    NULLIF(item.payload_json ->> 'reference_id', ''),
                    item.id::text
                )
            )
            FROM mission_items AS item
            WHERE item.mission_id = mission.mission_id
              AND item.item_type = 'evidence'
        )
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "110 is an irreversible Mission semantic-reference SSOT cutover; "
        "restore from backup if needed"
    )
