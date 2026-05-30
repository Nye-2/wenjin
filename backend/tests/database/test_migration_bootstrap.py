"""Tests for migration bootstrap mode detection."""

import pytest

from src.database.migration_bootstrap import (
    CREATE_ALL_BOOTSTRAP_STAMP_REVISION,
    THREAD_BOOTSTRAP_STAMP_REVISION,
    MigrationBootstrapMode,
    decide_bootstrap_mode,
    resolve_bootstrap_stamp_revision,
)


def test_decide_bootstrap_mode_upgrade_only_for_empty_database() -> None:
    assert decide_bootstrap_mode(set()) is MigrationBootstrapMode.UPGRADE_ONLY


def test_decide_bootstrap_mode_upgrade_only_when_version_table_exists() -> None:
    table_names = {"alembic_version", "users", "workspaces"}
    assert decide_bootstrap_mode(table_names) is MigrationBootstrapMode.UPGRADE_ONLY


def test_decide_bootstrap_mode_stamp_for_existing_schema_without_version_table() -> None:
    table_names = {"users", "workspaces", "papers"}
    assert decide_bootstrap_mode(table_names) is MigrationBootstrapMode.STAMP_THEN_UPGRADE


def test_decide_bootstrap_mode_rejects_unknown_existing_schema() -> None:
    with pytest.raises(ValueError, match="refusing to auto-stamp"):
        decide_bootstrap_mode({"custom_table"})


def test_resolve_bootstrap_stamp_revision_create_all_chat_schema() -> None:
    table_names = {"users", "chat_threads", "workspaces"}
    assert resolve_bootstrap_stamp_revision(table_names) == CREATE_ALL_BOOTSTRAP_STAMP_REVISION


def test_resolve_bootstrap_stamp_revision_thread_schema() -> None:
    table_names = {"users", "threads", "workspaces"}
    assert resolve_bootstrap_stamp_revision(table_names) == THREAD_BOOTSTRAP_STAMP_REVISION
