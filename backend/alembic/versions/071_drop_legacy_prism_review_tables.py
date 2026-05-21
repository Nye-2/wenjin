"""Drop legacy Prism review/source/protection tables.

Revision ID: 071_drop_legacy_prism_review_tables
Revises: 070_dataservice_projection_cleanup
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "071_drop_legacy_prism_review_tables"
down_revision: str | None = "070_dataservice_projection_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text("DROP TABLE IF EXISTS prism_source_links CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS prism_protected_sections CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS prism_review_items CASCADE"))
    conn.execute(sa.text("""
        INSERT INTO dataservice_migration_reports (
            id, migration_key, source_module, target_domain, status, summary,
            report_json, completed_at, created_at, updated_at
        )
        VALUES (
            md5('071:drop_legacy_prism_review_tables'),
            '071_drop_legacy_prism_review_tables',
            'legacy_prism_review_tables',
            'review_prism_provenance',
            'completed',
            'Dropped legacy Prism review/source/protection tables after runtime cutover to review_items, provenance_links, and prism_protected_scopes.',
            jsonb_build_object(
                'dropped_tables', jsonb_build_array(
                    'prism_review_items',
                    'prism_source_links',
                    'prism_protected_sections'
                ),
                'replacement_tables', jsonb_build_array(
                    'review_items',
                    'review_batches',
                    'provenance_links',
                    'prism_protected_scopes'
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
    raise RuntimeError("071_drop_legacy_prism_review_tables is irreversible")
