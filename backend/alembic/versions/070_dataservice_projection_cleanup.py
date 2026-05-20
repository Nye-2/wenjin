"""Record DataService projection cleanup stage.

Revision ID: 070_dataservice_projection_cleanup
Revises: 069_dataservice_rooms_hooks
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "070_dataservice_projection_cleanup"
down_revision: str | None = "069_dataservice_rooms_hooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text("""
        INSERT INTO dataservice_migration_reports (
            id, migration_key, source_module, target_domain, status, summary,
            report_json, completed_at, created_at, updated_at
        )
        VALUES (
            md5('070:dataservice_projection_cleanup'),
            '070_dataservice_projection_cleanup',
            'runtime_projections',
            'dataservice',
            'completed',
            'Cut migrated room and sandbox runtime projections to DataService APIs and guard against direct legacy model imports.',
            jsonb_build_object(
                'migrated_model_imports_blocked', jsonb_build_array(
                    'decision',
                    'memory_fact',
                    'workspace_task',
                    'sandbox'
                ),
                'projection_cleanup_version', 'projection_cleanup.v1'
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
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text("""
        DELETE FROM dataservice_migration_reports
        WHERE migration_key = '070_dataservice_projection_cleanup'
    """))
