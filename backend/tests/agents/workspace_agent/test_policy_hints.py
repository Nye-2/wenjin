"""DataService-backed MissionPolicy routing context tests."""

from __future__ import annotations

import pytest

from src.contracts.mission_policy import MissionPolicy
from src.dataservice_client.contracts.catalog import MissionPolicyPayload
from src.services.mission_policy_hints import load_mission_policy_hints
from src.services.mission_policy_loader import MissionPolicyLoader


def _record(*, description: str, enabled: bool = True) -> MissionPolicyPayload:
    item = next(
        item
        for item in MissionPolicyLoader().read_seed_items()
        if item["data"]["id"] == "sci_research"
    )
    raw = dict(item["data"])
    raw.pop("resolved_stage_contracts")
    raw.pop("content_hash")
    raw["enabled"] = enabled
    raw["display"] = {**raw["display"], "description": description}
    contract = MissionPolicy.model_validate(raw)
    data = contract.to_catalog_data(
        resolved_stage_contracts=item["data"]["resolved_stage_contracts"]
    )
    return MissionPolicyPayload(
        id=contract.id,
        workspace_type=contract.workspace_type,
        schema_version=contract.schema_version,
        enabled=enabled,
        policy_json=data,
        content_hash=data["content_hash"],
        source_path=item["source_path"],
    )


class CatalogClient:
    def __init__(self, records: list[MissionPolicyPayload]) -> None:
        self.records = records
        self.calls: list[tuple[str, bool]] = []

    async def list_mission_policies(self, *, workspace_type: str, enabled_only: bool):
        self.calls.append((workspace_type, enabled_only))
        return [
            item
            for item in self.records
            if item.workspace_type == workspace_type and (item.enabled or not enabled_only)
        ]


@pytest.mark.asyncio
async def test_policy_hints_refresh_from_versioned_catalog_without_process_cache() -> None:
    client = CatalogClient([_record(description="first")])
    first = await load_mission_policy_hints(client, "sci")  # type: ignore[arg-type]

    client.records = [_record(description="updated")]
    second = await load_mission_policy_hints(client, "sci")  # type: ignore[arg-type]

    assert first[0].summary == "first"
    assert second[0].summary == "updated"
    assert first[0].content_hash != second[0].content_hash
    assert client.calls == [("sci", True), ("sci", True)]


@pytest.mark.asyncio
async def test_disabled_policy_is_not_exposed_to_chat_routing() -> None:
    client = CatalogClient([_record(description="disabled", enabled=False)])

    assert await load_mission_policy_hints(client, "sci") == ()  # type: ignore[arg-type]
