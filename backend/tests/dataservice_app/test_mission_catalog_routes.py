"""DataService route contract tests for the Mission catalog."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.dataservice_app.routers import catalog
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


def _policy_row() -> SimpleNamespace:
    item = MissionPolicyLoader().read_seed_items()[0]
    data = item["data"]
    return SimpleNamespace(
        id=data["id"],
        workspace_type=data["workspace_type"],
        schema_version=data["schema_version"],
        enabled=data["enabled"],
        policy_json=data,
        content_hash=data["content_hash"],
        source_path=item["source_path"],
    )


def _skill_row() -> SimpleNamespace:
    item = SkillLoader().read_seed_items()[0]
    data = item["data"]
    return SimpleNamespace(
        id=data["id"],
        schema_version=data["schema_version"],
        enabled=data["enabled"],
        skill_json=data,
        content_hash=data["content_hash"],
        source_path=item["source_path"],
    )


def test_router_exposes_only_mission_policy_and_worker_skill_surfaces() -> None:
    paths = {route.path for route in catalog.router.routes}
    assert paths == {
        "/internal/v1/catalog/mission-policies",
        "/internal/v1/catalog/mission-policies/exists",
        "/internal/v1/catalog/mission-policies/{workspace_type}/{policy_id}",
        "/internal/v1/catalog/mission-policies/seed-load",
        "/internal/v1/catalog/worker-skills",
        "/internal/v1/catalog/worker-skills/exists",
        "/internal/v1/catalog/worker-skills/{skill_id}",
        "/internal/v1/catalog/worker-skills/seed-load",
    }


@pytest.mark.asyncio
async def test_get_routes_project_canonical_catalog_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = _policy_row()
    skill = _skill_row()
    service = SimpleNamespace(
        get_policy=AsyncMock(return_value=policy),
        get_skill=AsyncMock(return_value=skill),
    )
    monkeypatch.setattr(catalog, "MissionCatalogService", lambda *_args, **_kwargs: service)
    uow = SimpleNamespace(required_session=object())

    policy_response = await catalog.get_mission_policy(policy.workspace_type, policy.id, uow)
    skill_response = await catalog.get_worker_skill(skill.id, uow)

    assert policy_response["data"]["policy_json"] == policy.policy_json
    assert policy_response["data"]["content_hash"] == policy.content_hash
    assert skill_response["data"]["skill_json"] == skill.skill_json
    assert skill_response["data"]["content_hash"] == skill.content_hash


@pytest.mark.asyncio
async def test_get_routes_return_404_for_unknown_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SimpleNamespace(
        get_policy=AsyncMock(return_value=None),
        get_skill=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(catalog, "MissionCatalogService", lambda *_args, **_kwargs: service)
    uow = SimpleNamespace(required_session=object())

    with pytest.raises(HTTPException) as policy_error:
        await catalog.get_mission_policy("sci", "missing", uow)
    with pytest.raises(HTTPException) as skill_error:
        await catalog.get_worker_skill("missing", uow)
    assert policy_error.value.status_code == 404
    assert skill_error.value.status_code == 404
