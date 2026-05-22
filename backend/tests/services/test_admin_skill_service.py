"""Tests for AdminSkillService CRUD through DataService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.admin_skill_service import AdminSkillService

SAMPLE_SKILL_YAML = """
schema_version: capability_skill.v2
id: test-skill
enabled: true
display_name: Test Skill
description: Test
worker:
  category: writing
  subagent_type: react
  role_prompt: |
    You are a test agent.
io_contract:
  input_schema:
    type: object
  output_schema:
    type: object
context_access:
  room_reads: {}
  prism_context: summary
tool_policy:
  allowed_tools: []
sandbox_access:
  mode: none
  profiles: []
quality_gates: []
"""


class _SkillCatalogFake:
    def __init__(self) -> None:
        self.records: dict[str, SimpleNamespace] = {}
        self.admin_logs: list[object] = []
        self.record_catalog_admin_log = AsyncMock(side_effect=self._record_admin_log)

    async def list_catalog_skills(self):
        return sorted(self.records.values(), key=lambda item: item.id)

    async def get_catalog_skill(self, skill_id: str):
        return self.records.get(skill_id)

    async def upsert_catalog_skill(self, *, skill_id: str, command):
        data = dict(command.data)
        if "subagent_type" not in data and "worker_type" in data:
            data["subagent_type"] = data["worker_type"]
        data.setdefault("skill_json", dict(command.data))
        record = SimpleNamespace(**data)
        self.records[skill_id] = record
        return record

    async def delete_catalog_skill(self, skill_id: str):
        return self.records.pop(skill_id, None) is not None

    async def set_catalog_skill_enabled(self, *, skill_id: str, command):
        record = self.records.get(skill_id)
        if record is None:
            return None
        record.enabled = command.enabled
        return record

    async def _record_admin_log(self, command):
        self.admin_logs.append(command)
        return SimpleNamespace(id=f"log-{len(self.admin_logs)}")


@pytest.fixture
def service():
    fake_validator = MagicMock()
    fake_validator.validate_skill = AsyncMock(return_value=[])
    dataservice = _SkillCatalogFake()
    svc = AdminSkillService(db=AsyncMock(), dataservice=dataservice)
    svc.validator = fake_validator
    svc._test_dataservice = dataservice
    return svc


@pytest.mark.asyncio
async def test_create_skill_persists(service):
    skill = await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    assert skill.id == "test-skill"
    assert skill.subagent_type == "react"
    service._test_dataservice.record_catalog_admin_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_subagent_type_fails(service):
    service.validator.validate_skill = AsyncMock(
        return_value=["subagent_type 'bogus_type' not in v2 subagent registry"]
    )
    bad = SAMPLE_SKILL_YAML.replace("subagent_type: react", "subagent_type: bogus_type")
    with pytest.raises(ValueError, match="bogus_type"):
        await service.create(yaml_text=bad, admin_id="admin-uuid")


@pytest.mark.asyncio
async def test_get_returns_created_skill(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.get("test-skill")
    assert skill is not None
    assert skill.display_name == "Test Skill"


@pytest.mark.asyncio
async def test_list_all_returns_skills(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    items = await service.list_all()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_update_modifies_fields(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    updated = SAMPLE_SKILL_YAML.replace("Test Skill", "Updated Skill")
    skill = await service.update(
        skill_id="test-skill",
        yaml_text=updated,
        admin_id="admin-uuid",
    )
    assert skill.display_name == "Updated Skill"


@pytest.mark.asyncio
async def test_update_rejects_id_mismatch(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    with pytest.raises(ValueError, match="must match"):
        await service.update(
            skill_id="wrong-id",
            yaml_text=SAMPLE_SKILL_YAML,
            admin_id="admin-uuid",
        )


@pytest.mark.asyncio
async def test_delete_removes_skill(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    await service.delete(skill_id="test-skill", admin_id="admin-uuid")
    skill = await service.get("test-skill")
    assert skill is None


@pytest.mark.asyncio
async def test_toggle_flips_enabled(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.toggle(skill_id="test-skill", admin_id="admin-uuid")
    assert skill.enabled is False
    skill2 = await service.toggle(skill_id="test-skill", admin_id="admin-uuid")
    assert skill2.enabled is True


@pytest.mark.asyncio
async def test_to_yaml_text_round_trips(service):
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    skill = await service.get("test-skill")
    yaml_text = service.to_yaml_text(skill)
    assert "test-skill" in yaml_text
    assert "react" in yaml_text


@pytest.mark.asyncio
async def test_create_does_not_commit_gateway_session(service):
    service.db.commit = AsyncMock()
    await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    service.db.commit.assert_not_awaited()
