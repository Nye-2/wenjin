"""MissionPolicy and WorkerSkill catalog domain tests."""

from __future__ import annotations

from typing import Any

import pytest

from src.database.models.mission_catalog import MissionPolicyRecord, WorkerSkillRecord
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


class _Session:
    def __init__(self) -> None:
        self.repository: _Repository | None = None
        self.flushes = 0
        self.commits = 0

    def add(self, record: object) -> None:
        assert self.repository is not None
        if isinstance(record, MissionPolicyRecord):
            self.repository.policies[(record.workspace_type, record.id)] = record
        elif isinstance(record, WorkerSkillRecord):
            self.repository.skills[record.id] = record
        else:  # pragma: no cover - protects the fake itself
            raise AssertionError(f"unexpected record: {type(record)!r}")

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


class _Repository:
    def __init__(self) -> None:
        self.policies: dict[tuple[str, str], MissionPolicyRecord] = {}
        self.skills: dict[str, WorkerSkillRecord] = {}

    async def list_policies(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[MissionPolicyRecord]:
        return [row for (row_workspace_type, _), row in self.policies.items() if (workspace_type is None or workspace_type == row_workspace_type) and (not enabled_only or row.enabled)]

    async def get_policy(self, *, policy_id: str, workspace_type: str) -> MissionPolicyRecord | None:
        return self.policies.get((workspace_type, policy_id))

    async def list_skills(self, *, enabled_only: bool = False) -> list[WorkerSkillRecord]:
        return [row for row in self.skills.values() if not enabled_only or row.enabled]

    async def get_skill(self, skill_id: str) -> WorkerSkillRecord | None:
        return self.skills.get(skill_id)

    async def clear_policies(self) -> None:
        self.policies.clear()

    async def clear_skills(self) -> None:
        self.skills.clear()


def _service() -> tuple[MissionCatalogService, _Repository, _Session]:
    session = _Session()
    repository = _Repository()
    session.repository = repository
    service = MissionCatalogService(session, autocommit=True)  # type: ignore[arg-type]
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def _policy_item() -> dict[str, Any]:
    return MissionPolicyLoader().read_seed_items()[0]


def _skill_item() -> dict[str, Any]:
    return SkillLoader().read_seed_items()[0]


@pytest.mark.asyncio
async def test_loads_canonical_records_and_is_idempotent() -> None:
    service, repository, session = _service()
    policy_item = _policy_item()
    skill_item = _skill_item()

    assert await service.load_policies([policy_item], overwrite=False) == 1
    assert await service.load_skills([skill_item], overwrite=False) == 1
    assert await service.load_policies([policy_item], overwrite=False) == 0
    assert await service.load_skills([skill_item], overwrite=False) == 0

    policy_data = policy_item["data"]
    policy = repository.policies[(policy_data["workspace_type"], policy_data["id"])]
    skill = repository.skills[skill_item["data"]["id"]]
    assert policy.policy_json == policy_data
    assert policy.content_hash == policy_data["content_hash"]
    assert skill.skill_json == skill_item["data"]
    assert skill.content_hash == skill_item["data"]["content_hash"]
    assert session.commits == 4


@pytest.mark.asyncio
async def test_get_list_has_and_overwrite_share_one_repository_truth() -> None:
    service, repository, _ = _service()
    policy_item = _policy_item()
    skill_item = _skill_item()
    await service.load_policies([policy_item], overwrite=False)
    await service.load_skills([skill_item], overwrite=False)

    policy_data = policy_item["data"]
    assert await service.has_policies() is True
    assert await service.has_skills() is True
    assert (
        await service.get_policy(
            policy_id=str(policy_data["id"]),
            workspace_type=str(policy_data["workspace_type"]),
        )
    ) is repository.policies[(policy_data["workspace_type"], policy_data["id"])]
    assert await service.get_skill(str(skill_item["data"]["id"])) is repository.skills[skill_item["data"]["id"]]

    await service.load_policies([policy_item], overwrite=True)
    await service.load_skills([skill_item], overwrite=True)
    assert len(repository.policies) == 1
    assert len(repository.skills) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["policy", "skill"])
async def test_rejects_tampered_content_hash(kind: str) -> None:
    service, _, _ = _service()
    item = _policy_item() if kind == "policy" else _skill_item()
    item["data"]["content_hash"] = "0" * 64

    with pytest.raises(ValueError, match="content_hash"):
        if kind == "policy":
            await service.load_policies([item], overwrite=False)
        else:
            await service.load_skills([item], overwrite=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["policy", "skill"])
async def test_rejects_duplicate_seed_identities(kind: str) -> None:
    service, _, _ = _service()
    item = _policy_item() if kind == "policy" else _skill_item()

    with pytest.raises(ValueError, match="duplicate identities"):
        if kind == "policy":
            await service.load_policies([item, item], overwrite=False)
        else:
            await service.load_skills([item, item], overwrite=False)
