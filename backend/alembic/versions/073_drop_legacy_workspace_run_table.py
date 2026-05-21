"""Drop legacy workspace_run table.

Revision ID: 073_drop_legacy_workspace_run_table
Revises: 072_drop_legacy_reference_tables
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "073_drop_legacy_workspace_run_table"
down_revision: str | None = "072_drop_legacy_reference_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text("DROP TABLE IF EXISTS workspace_run CASCADE"))
    conn.execute(sa.text("""
        INSERT INTO dataservice_migration_reports (
            id, migration_key, source_module, target_domain, status, summary,
            report_json, completed_at, created_at, updated_at
        )
        VALUES (
            md5('073:drop_legacy_workspace_run_table'),
            '073_drop_legacy_workspace_run_table',
            'legacy_workspace_run',
            'execution',
            'completed',
            'Dropped legacy workspace_run table after runtime run state moved to Execution DataService projections.',
            jsonb_build_object(
                'dropped_tables', jsonb_build_array('workspace_run'),
                'replacement_tables', jsonb_build_array(
                    'executions',
                    'execution_events',
                    'execution_nodes'
                ),
                'notes', jsonb_build_array(
                    'subagent_task_records.run_id remains as an unconstrained historical id field',
                    'subagent_task_records.execution_id is the canonical execution foreign key'
                )
            ),
            now(),
            now(),
            now()
        )
        ON CONFLICT (migration_key) DO UPDATE SET
            status = EXCLUDED.status,
            summary = EXCLUDED.summary,
            report_json = EXCLUDED.report_json,
            completed_at = EXCLUDED.completed_at,
            updated_at = now()
    """))


def downgrade() -> None:
    raise RuntimeError("073_drop_legacy_workspace_run_table is irreversible")
