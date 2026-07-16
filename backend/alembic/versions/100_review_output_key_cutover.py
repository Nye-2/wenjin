"""make Mission review outputs single-current by semantic key

Revision ID: 100_review_output_key_cutover
Revises: 099_thread_skill_cutover
"""

from alembic import op
import sqlalchemy as sa

revision = "100_review_output_key_cutover"
down_revision = "099_thread_skill_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_review_items",
        sa.Column("output_key", sa.String(length=160), nullable=True),
    )
    op.execute(
        """
        UPDATE mission_review_items
        SET output_key = COALESCE(
            NULLIF(preview_json ->> 'output_key', ''),
            NULLIF(preview_json ->> 'artifact_kind', ''),
            target_kind || ':' || review_item_id
        )
        """
    )
    op.alter_column("mission_review_items", "output_key", nullable=False)
    op.create_index(
        "ix_mission_review_items_output",
        "mission_review_items",
        ["mission_id", "output_key", "created_at"],
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                review_item_id,
                first_value(title) OVER (
                    PARTITION BY mission_id, output_key
                    ORDER BY created_at ASC, review_item_id ASC
                ) AS canonical_title,
                row_number() OVER (
                    PARTITION BY mission_id, output_key
                    ORDER BY created_at DESC, review_item_id DESC
                ) AS newest_rank
            FROM mission_review_items
            WHERE status <> 'committed'
        )
        UPDATE mission_review_items AS item
        SET title = ranked.canonical_title
        FROM ranked
        WHERE item.review_item_id = ranked.review_item_id
          AND ranked.newest_rank = 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                review_item_id,
                row_number() OVER (
                    PARTITION BY mission_id, output_key
                    ORDER BY created_at DESC, review_item_id DESC
                ) AS newest_rank
            FROM mission_review_items
            WHERE status <> 'committed'
        )
        UPDATE mission_review_items AS item
        SET
            status = 'superseded',
            suggested_selected = false,
            decision_json = '{"decision":"superseded","reason":"A newer candidate now represents this output."}'::jsonb,
            decided_by = NULL,
            decided_at = now(),
            updated_at = now()
        FROM ranked
        WHERE item.review_item_id = ranked.review_item_id
          AND ranked.newest_rank > 1
        """
    )
    op.execute(
        """
        UPDATE mission_runs AS run
        SET pending_review_count = counts.pending_count
        FROM (
            SELECT
                run_id.mission_id,
                count(item.review_item_id) FILTER (WHERE item.status = 'pending') AS pending_count
            FROM mission_runs AS run_id
            LEFT JOIN mission_review_items AS item ON item.mission_id = run_id.mission_id
            GROUP BY run_id.mission_id
        ) AS counts
        WHERE run.mission_id = counts.mission_id
        """
    )


def downgrade() -> None:
    raise RuntimeError("100 is an irreversible development cutover; reseed instead")
