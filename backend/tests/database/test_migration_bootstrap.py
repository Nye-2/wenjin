"""Tests for migration bootstrap mode detection."""

import pytest

from src.database.migration_bootstrap import (
    MigrationBootstrapMode,
    decide_bootstrap_mode,
)


def test_decide_bootstrap_mode_upgrade_only_for_empty_database() -> None:
    assert decide_bootstrap_mode(set()) is MigrationBootstrapMode.UPGRADE_ONLY


def test_decide_bootstrap_mode_upgrade_only_when_version_table_exists() -> None:
    table_names = {"alembic_version", "users", "workspaces"}
    assert decide_bootstrap_mode(table_names) is MigrationBootstrapMode.UPGRADE_ONLY


def test_decide_bootstrap_mode_stamp_for_legacy_schema_without_version_table() -> None:
    table_names = {"users", "workspaces", "papers"}
    assert decide_bootstrap_mode(table_names) is MigrationBootstrapMode.STAMP_THEN_UPGRADE


def test_decide_bootstrap_mode_rejects_unknown_existing_schema() -> None:
    with pytest.raises(ValueError, match="refusing to auto-stamp"):
        decide_bootstrap_mode({"custom_table"})
