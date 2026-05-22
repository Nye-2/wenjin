"""Tests for AdminCapabilityService CRUD operations through DataService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.admin_capability_service import AdminCapabilityService

SAMPLE_YAML = """
id: test_cap
workspace_type: thesis
display_name: Test Capability
intent_description: for testing
brief_schema:
  type: object
graph_template:
  phases:
    - name: phase1
      tasks:
        - name: t1
          subagent_type: react
ui_meta:
  icon: search
  color: purple
"""


class _CatalogFake:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], SimpleNamespace] = {}
        self.admin_logs: list[object] = []
        self.record_catalog_admin_log = AsyncMock(side_effect=self._record_admin_log)

    async def list_catalog_capabilities(self):
        return sorted(
            self.records.values(),
            key=lambda item: (item.workspace_type, item.id),
        )

    async def get_catalog_capability(self, *, capability_id: str, workspace_type: str):
        return self.records.get((workspace_type, capability_id))

    async def upsert_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        command,
    ):
        record = SimpleNamespace(**command.data)
        self.records[(workspace_type, capability_id)] = record
        return record

    async def delete_catalog_capability(self, *, capability_id: str, workspace_type: str):
        return self.records.pop((workspace_type, capability_id), None) is not None

    async def set_catalog_capability_enabled(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        command,
    ):
        record = self.records.get((workspace_type, capability_id))
        if record is None:
            return None
        record.enabled = command.enabled
        return record

    async def _record_admin_log(self, command):
        self.admin_logs.append(command)
        return SimpleNamespace(id=f"log-{len(self.admin_logs)}")


@pytest.fixture
def service():
    bus = AsyncMock()
    dataservice = _CatalogFake()
    fake_validator = MagicMock()
    fake_validator.validate_capability = AsyncMock(return_value=[])
    svc = AdminCapabilityService(db=AsyncMock(), event_bus=bus, dataservice=dataservice)
    svc.validator = fake_validator
    svc._test_dataservice = dataservice
    return svc


@pytest.mark.asyncio
async def test_create_persists_capability(service):
    cap = await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    assert cap.id == "test_cap"
    assert cap.workspace_type == "thesis"
    assert cap.ui_meta["icon"] == "search"
    service.event_bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": "test_cap", "workspace_type": "thesis"},
    )
    service._test_dataservice.record_catalog_admin_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_with_invalid_yaml_raises(service):
    with pytest.raises(ValueError, match="yaml"):
        await service.create(yaml_text="!!!not yaml{{{", admin_id="admin-uuid")
    service.event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_get_returns_created_capability(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.get("test_cap", "thesis")
    assert cap is not None
    assert cap.display_name == "Test Capability"


@pytest.mark.asyncio
async def test_list_all_returns_capabilities(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    items = await service.list_all()
    assert len(items) == 1
    assert items[0].id == "test_cap"


@pytest.mark.asyncio
async def test_update_modifies_fields(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    updated_yaml = SAMPLE_YAML.replace("Test Capability", "Updated Name")
    cap = await service.update(
        capability_id="test_cap",
        workspace_type="thesis",
        yaml_text=updated_yaml,
        admin_id="admin-uuid",
    )
    assert cap.display_name == "Updated Name"


@pytest.mark.asyncio
async def test_update_rejects_id_mismatch(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    with pytest.raises(ValueError, match="must match"):
        await service.update(
            capability_id="wrong_id",
            workspace_type="thesis",
            yaml_text=SAMPLE_YAML,
            admin_id="admin-uuid",
        )


@pytest.mark.asyncio
async def test_delete_removes_capability(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    await service.delete(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    cap = await service.get("test_cap", "thesis")
    assert cap is None
    service.event_bus.publish.assert_awaited()


@pytest.mark.asyncio
async def test_toggle_flips_enabled(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.toggle(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    assert cap.enabled is False
    cap2 = await service.toggle(
        capability_id="test_cap",
        workspace_type="thesis",
        admin_id="admin-uuid",
    )
    assert cap2.enabled is True


@pytest.mark.asyncio
async def test_validate_returns_errors_without_writing(service):
    bad_yaml = SAMPLE_YAML.replace(
        "subagent_type: react", "subagent_type: nonexistent"
    )
    service.validator.validate_capability = AsyncMock(
        return_value=["subagent_type 'nonexistent' not in v2 subagent registry"]
    )
    errors = await service.validate(yaml_text=bad_yaml)
    assert any("nonexistent" in e for e in errors)
    service.event_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_to_yaml_text_round_trips(service):
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    cap = await service.get("test_cap", "thesis")
    yaml_text = service.to_yaml_text(cap)
    assert "test_cap" in yaml_text
    assert "thesis" in yaml_text


@pytest.mark.asyncio
async def test_create_does_not_commit_gateway_session(service):
    service.db.commit = AsyncMock()
    await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    service.db.commit.assert_not_awaited()
