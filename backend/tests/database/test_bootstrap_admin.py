"""Deployment bootstrap tests for the canonical Mission catalog."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.database import bootstrap_admin
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


class FakeSession:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def __init__(self) -> None:
        self.commit = AsyncMock()


class FakeCatalog:
    _skill_items = SkillLoader().read_seed_items()
    skills = [
        SimpleNamespace(
            id=item["data"]["id"],
            skill_json=item["data"],
            content_hash=item["data"]["content_hash"],
        )
        for item in _skill_items
    ]
    _policy_items = MissionPolicyLoader().read_seed_items()
    policies = [
        SimpleNamespace(
            id=item["data"]["id"],
            workspace_type=item["data"]["workspace_type"],
            content_hash=item["data"]["content_hash"],
            policy_json=item["data"],
        )
        for item in _policy_items
    ]

    def __init__(self, _session, *, autocommit: bool) -> None:
        assert autocommit is False

    async def list_skills(self, *, enabled_only: bool = False):
        assert enabled_only is True
        return list(self.skills)

    async def list_policies(self, *, enabled_only: bool = False):
        assert enabled_only is True
        return list(self.policies)


@pytest.mark.asyncio
async def test_bootstrap_seeds_skills_before_policies_and_validates_all_workspaces(
    monkeypatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(bootstrap_admin, "MissionCatalogService", FakeCatalog)
    monkeypatch.setattr(
        bootstrap_admin.SkillLoader,
        "sync_with_service",
        AsyncMock(side_effect=lambda _service: order.append("skills") or 15),
    )
    monkeypatch.setattr(
        bootstrap_admin.MissionPolicyLoader,
        "sync_with_service",
        AsyncMock(side_effect=lambda _service: order.append("policies") or 6),
    )
    session = FakeSession()

    assert await bootstrap_admin.seed_mission_catalog(session) == (15, 6)
    assert order == ["skills", "policies"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_catalog_is_a_fatal_bootstrap_error(monkeypatch) -> None:
    class EmptyCatalog(FakeCatalog):
        skills = []
        policies = []

    monkeypatch.setattr(bootstrap_admin, "MissionCatalogService", EmptyCatalog)
    monkeypatch.setattr(
        bootstrap_admin.SkillLoader,
        "sync_with_service",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        bootstrap_admin.MissionPolicyLoader,
        "sync_with_service",
        AsyncMock(return_value=0),
    )

    with pytest.raises(RuntimeError, match="no enabled policy"):
        await bootstrap_admin.seed_mission_catalog(FakeSession())


@pytest.mark.asyncio
async def test_concurrent_bootstrap_calls_are_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap_admin, "MissionCatalogService", FakeCatalog)
    skill_sync = AsyncMock(side_effect=[15, 0])
    policy_sync = AsyncMock(side_effect=[6, 0])
    monkeypatch.setattr(bootstrap_admin.SkillLoader, "sync_with_service", skill_sync)
    monkeypatch.setattr(bootstrap_admin.MissionPolicyLoader, "sync_with_service", policy_sync)

    results = await asyncio.gather(
        bootstrap_admin.seed_mission_catalog(FakeSession()),
        bootstrap_admin.seed_mission_catalog(FakeSession()),
    )

    assert sorted(results) == [(0, 0), (15, 6)]


def test_bootstrap_has_no_retired_catalog_loader() -> None:
    source = bootstrap_admin.__file__
    text = open(source, encoding="utf-8").read()
    assert "CapabilityLoader" not in text
    assert "AgentTemplateLoader" not in text
    assert "WARN: skill seed failed" not in text
