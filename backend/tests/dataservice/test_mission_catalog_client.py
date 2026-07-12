"""Typed DataService client contract tests for the Mission catalog."""

from __future__ import annotations

from typing import Any

import pytest

from src.dataservice_client.catalog_client import CatalogDataServiceClientMixin
from src.dataservice_client.contracts.catalog import CatalogSeedLoadPayload
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


class _Client(CatalogDataServiceClientMixin):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.requests.append((method, path, kwargs))
        return self.responses.pop(0)


def _policy_payload() -> dict[str, Any]:
    item = MissionPolicyLoader().read_seed_items()[0]
    data = item["data"]
    return {
        "id": data["id"],
        "workspace_type": data["workspace_type"],
        "schema_version": data["schema_version"],
        "enabled": data["enabled"],
        "policy_json": data,
        "content_hash": data["content_hash"],
        "source_path": item["source_path"],
    }


def _skill_payload() -> dict[str, Any]:
    item = SkillLoader().read_seed_items()[0]
    data = item["data"]
    return {
        "id": data["id"],
        "schema_version": data["schema_version"],
        "enabled": data["enabled"],
        "skill_json": data,
        "content_hash": data["content_hash"],
        "source_path": item["source_path"],
    }


@pytest.mark.asyncio
async def test_typed_list_get_and_exists_methods() -> None:
    policy = _policy_payload()
    skill = _skill_payload()
    client = _Client(
        [
            {"data": [policy]},
            {"data": policy},
            {"data": {"exists": True}},
            {"data": [skill]},
            {"data": skill},
            {"data": {"exists": True}},
        ]
    )

    assert (await client.list_mission_policies(workspace_type="sci", enabled_only=True))[0].id == policy["id"]
    assert (await client.get_mission_policy(policy_id=policy["id"], workspace_type="sci")).policy_json == policy["policy_json"]
    assert await client.has_mission_policies() is True
    assert (await client.list_worker_skills(enabled_only=True))[0].id == skill["id"]
    assert (await client.get_worker_skill(skill["id"])).skill_json == skill["skill_json"]
    assert await client.has_worker_skills() is True

    assert client.requests[1][1] == f"/internal/v1/catalog/mission-policies/sci/{policy['id']}"
    assert client.requests[4][1] == f"/internal/v1/catalog/worker-skills/{skill['id']}"


@pytest.mark.asyncio
async def test_typed_seed_load_methods_send_canonical_payload() -> None:
    client = _Client([{"data": {"loaded": 2}}, {"data": {"loaded": 1}}])
    command = CatalogSeedLoadPayload(overwrite=True, items=[])

    assert (await client.load_mission_policy_seed_items(command)).loaded == 2
    assert (await client.load_worker_skill_seed_items(command)).loaded == 1
    assert client.requests == [
        (
            "POST",
            "/internal/v1/catalog/mission-policies/seed-load",
            {"json": {"overwrite": True, "items": []}},
        ),
        (
            "POST",
            "/internal/v1/catalog/worker-skills/seed-load",
            {"json": {"overwrite": True, "items": []}},
        ),
    ]
