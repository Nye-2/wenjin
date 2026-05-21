"""Migration contract tests for workspace membership invariants."""

from __future__ import annotations

from pathlib import Path


def test_workspace_owner_membership_migration_declares_deferred_constraints() -> None:
    migration = Path("alembic/versions/075_enforce_workspace_owner_membership.py").read_text(encoding="utf-8")

    assert "dataservice_assert_workspace_active_owner" in migration
    assert "CREATE CONSTRAINT TRIGGER ck_workspaces_active_owner" in migration
    assert "CREATE CONSTRAINT TRIGGER ck_workspace_memberships_active_owner" in migration
    assert "DEFERRABLE INITIALLY DEFERRED" in migration
    assert "workspace % must have at least one active owner membership" in migration
