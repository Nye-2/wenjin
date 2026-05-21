"""Enforce active owner membership for every workspace.

Revision ID: 075_enforce_workspace_owner_membership
Revises: 074_drop_legacy_thread_messages_column
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "075_enforce_workspace_owner_membership"
down_revision: str | None = "074_drop_legacy_thread_messages_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    missing_owner_count = conn.execute(
        sa.text(
            """
            SELECT count(*)
            FROM workspaces w
            WHERE NOT EXISTS (
                SELECT 1
                FROM workspace_memberships wm
                WHERE wm.workspace_id = w.id
                  AND wm.role = 'owner'
                  AND wm.status = 'active'
            )
            """
        )
    ).scalar_one()
    if missing_owner_count:
        raise RuntimeError(
            "Cannot enforce workspace owner membership invariant: "
            f"{missing_owner_count} workspace(s) have no active owner membership."
        )

    op.drop_index("ix_workspace_memberships_workspace_role", table_name="workspace_memberships")
    op.create_index(
        "ix_workspace_memberships_workspace_role_status",
        "workspace_memberships",
        ["workspace_id", "role", "status"],
        unique=False,
    )

    conn.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION dataservice_assert_workspace_active_owner(p_workspace_id text)
            RETURNS void AS $$
            BEGIN
                IF p_workspace_id IS NULL THEN
                    RETURN;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM workspaces
                    WHERE id = p_workspace_id
                ) THEN
                    RETURN;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM workspace_memberships
                    WHERE workspace_id = p_workspace_id
                      AND role = 'owner'
                      AND status = 'active'
                ) THEN
                    RAISE EXCEPTION
                        'workspace % must have at least one active owner membership',
                        p_workspace_id
                        USING ERRCODE = '23514';
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION dataservice_workspace_owner_invariant_trigger()
            RETURNS trigger AS $$
            BEGIN
                IF TG_TABLE_NAME = 'workspace_memberships' THEN
                    IF TG_OP IN ('UPDATE', 'DELETE') THEN
                        PERFORM dataservice_assert_workspace_active_owner(OLD.workspace_id);
                    END IF;
                    IF TG_OP IN ('INSERT', 'UPDATE') THEN
                        PERFORM dataservice_assert_workspace_active_owner(NEW.workspace_id);
                    END IF;
                    RETURN COALESCE(NEW, OLD);
                END IF;

                IF TG_TABLE_NAME = 'workspaces' AND TG_OP <> 'DELETE' THEN
                    PERFORM dataservice_assert_workspace_active_owner(NEW.id);
                END IF;

                RETURN COALESCE(NEW, OLD);
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE CONSTRAINT TRIGGER ck_workspaces_active_owner
            AFTER INSERT OR UPDATE ON workspaces
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION dataservice_workspace_owner_invariant_trigger();

            CREATE CONSTRAINT TRIGGER ck_workspace_memberships_active_owner
            AFTER INSERT OR UPDATE OR DELETE ON workspace_memberships
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION dataservice_workspace_owner_invariant_trigger();
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO dataservice_migration_reports (
                id, migration_key, source_module, target_domain, status, summary,
                report_json, completed_at, created_at, updated_at
            )
            VALUES (
                md5('075:enforce_workspace_owner_membership'),
                '075_enforce_workspace_owner_membership',
                'workspace_memberships',
                'workspace',
                'completed',
                'Enforced at least one active owner membership per workspace with a deferred PostgreSQL constraint trigger.',
                jsonb_build_object(
                    'enforced_tables', jsonb_build_array('workspaces', 'workspace_memberships'),
                    'constraint_triggers', jsonb_build_array(
                        'ck_workspaces_active_owner',
                        'ck_workspace_memberships_active_owner'
                    ),
                    'index', 'ix_workspace_memberships_workspace_role_status'
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
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("DROP TRIGGER IF EXISTS ck_workspace_memberships_active_owner ON workspace_memberships"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS ck_workspaces_active_owner ON workspaces"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS dataservice_workspace_owner_invariant_trigger()"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS dataservice_assert_workspace_active_owner(text)"))
    op.drop_index("ix_workspace_memberships_workspace_role_status", table_name="workspace_memberships")
    op.create_index(
        "ix_workspace_memberships_workspace_role",
        "workspace_memberships",
        ["workspace_id", "role"],
        unique=False,
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM dataservice_migration_reports
            WHERE migration_key = '075_enforce_workspace_owner_membership'
            """
        )
    )
