"""add dispatch fencing and mission ledger operation receipts

Revision ID: 092_mission_runtime_reliability
Revises: 091_review_commit_consistency
"""

import sqlalchemy as sa
from alembic import op

revision = "092_mission_runtime_reliability"
down_revision = "091_review_commit_consistency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mission_runs", sa.Column("dispatch_owner", sa.String(160), nullable=True))
    op.add_column(
        "mission_runs",
        sa.Column("dispatch_epoch", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "mission_runs",
        sa.Column("dispatch_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_mission_runs_dispatch_epoch", "mission_runs", "dispatch_epoch >= 0"
    )
    op.create_check_constraint(
        "ck_mission_runs_dispatch_pair",
        "mission_runs",
        "(dispatch_owner IS NULL AND dispatch_expires_at IS NULL) OR "
        "(dispatch_owner IS NOT NULL AND dispatch_expires_at IS NOT NULL)",
    )
    op.drop_constraint("ck_mission_runs_terminal_quiescent", "mission_runs", type_="check")
    op.create_check_constraint(
        "ck_mission_runs_terminal_quiescent",
        "mission_runs",
        "status NOT IN ('completed', 'failed', 'cancelled') OR "
        "(lease_owner IS NULL AND lease_expires_at IS NULL "
        "AND dispatch_owner IS NULL AND dispatch_expires_at IS NULL "
        "AND next_wakeup_at IS NULL)",
    )

    op.drop_index("ix_mission_runs_workspace_updated", table_name="mission_runs")
    op.drop_index("ix_mission_runs_scheduler", table_name="mission_runs")
    op.create_index(
        "ix_mission_runs_workspace_updated_mission",
        "mission_runs",
        ["workspace_id", "updated_at", "mission_id"],
    )
    op.create_index(
        "ix_mission_runs_due_wakeup",
        "mission_runs",
        ["next_wakeup_at", "dispatch_expires_at"],
        postgresql_where=sa.text(
            "status IN ('created', 'planning', 'running', 'waiting') "
            "AND next_wakeup_at IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_mission_runs_expired_driver",
        "mission_runs",
        ["lease_expires_at", "dispatch_expires_at"],
        postgresql_where=sa.text(
            "status IN ('created', 'planning', 'running', 'waiting') "
            "AND lease_expires_at IS NOT NULL"
        ),
    )

    # mission_id already has a dedicated FK index; the composite index is the
    # scheduler access path and was the accidental duplicate.
    op.drop_index("ix_task_records_mission_status", table_name="task_records")


def downgrade() -> None:
    raise RuntimeError("092 is an irreversible development cutover; reseed instead")
