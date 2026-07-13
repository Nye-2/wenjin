from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy.dialects.postgresql import ENUM


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "087_model_capability_profile.py"
    )
    spec = importlib.util.spec_from_file_location("migration_087", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_is_chained_after_mission_cutover() -> None:
    migration = _migration_module()

    assert migration.revision == "087_model_capability_profile"
    assert migration.down_revision == "086_mission_runtime_cutover"


def test_historical_migration_does_not_bless_new_release_models() -> None:
    migration = _migration_module()
    profile, evidence = migration._assessment(
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://api.nainai.love/v1",
        generation_api="chat_completions",
    )
    assert profile["native_web_search"] is False
    assert profile["protocol_conformance"] is False
    assert profile["reasoning_efforts"] == []
    assert evidence["checks"][0]["detail_code"] == "not_probed"


def test_generation_api_updates_use_the_postgresql_enum_type() -> None:
    migration = _migration_module()
    enum_type = migration.postgresql.ENUM(
        "chat_completions",
        "responses",
        name="model_generation_api",
    )

    assert isinstance(enum_type, ENUM)
