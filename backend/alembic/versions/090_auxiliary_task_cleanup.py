"""remove feature execution fields from auxiliary task records

Revision ID: 090_auxiliary_task_cleanup
Revises: 089_mission_policy_catalog
"""

from alembic import op

revision = "090_auxiliary_task_cleanup"
down_revision = "089_mission_policy_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_task_records_active_dedupe_lookup", table_name="task_records")
    op.drop_index("ix_task_records_dedupe_lookup", table_name="task_records")
    op.drop_index("ix_task_workspace_feature_status", table_name="task_records")
    op.drop_index("ix_task_records_feature_id", table_name="task_records")
    op.drop_column("task_records", "action")
    op.drop_column("task_records", "feature_id")
    op.create_index(
        "ix_task_records_mission_status",
        "task_records",
        ["mission_id", "status"],
    )


def downgrade() -> None:
    raise RuntimeError("090 is an irreversible development cutover; reseed instead")
