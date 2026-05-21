"""Drop legacy reference library tables.

Revision ID: 072_drop_legacy_reference_tables
Revises: 071_drop_legacy_prism_review_tables
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "072_drop_legacy_reference_tables"
down_revision: str | None = "071_drop_legacy_prism_review_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_usage_events CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_text_units CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_outline_nodes CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_external_ids CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_assets CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reference_bibtex_snapshots CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS workspace_references CASCADE"))
    conn.execute(sa.text("""
        INSERT INTO dataservice_migration_reports (
            id, migration_key, source_module, target_domain, status, summary,
            report_json, completed_at, created_at, updated_at
        )
        VALUES (
            md5('072:drop_legacy_reference_tables'),
            '072_drop_legacy_reference_tables',
            'legacy_reference_tables',
            'source_provenance_assets',
            'completed',
            'Dropped legacy reference tables after runtime cutover to sources, source_assets, source_text_units, source_bibtex_snapshots, and provenance_links.',
            jsonb_build_object(
                'dropped_tables', jsonb_build_array(
                    'workspace_references',
                    'reference_external_ids',
                    'reference_assets',
                    'reference_outline_nodes',
                    'reference_text_units',
                    'reference_usage_events',
                    'reference_bibtex_snapshots'
                ),
                'replacement_tables', jsonb_build_array(
                    'sources',
                    'source_external_ids',
                    'workspace_assets',
                    'source_assets',
                    'source_outline_nodes',
                    'source_text_units',
                    'source_bibtex_snapshots',
                    'provenance_links'
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
    raise RuntimeError("072_drop_legacy_reference_tables is irreversible")
