"""Tests for canonical capability seed loading through DataService."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.capability_loader import CapabilityLoader


class _SeedCatalogFake:
    def __init__(self) -> None:
        self.records: list[SimpleNamespace] = []
        self.has_catalog_capabilities = AsyncMock(side_effect=self._has_capabilities)
        self.load_catalog_capability_seed_items = AsyncMock(side_effect=self._load_items)
        self.list_catalog_capabilities = AsyncMock(side_effect=self._list_capabilities)

    async def _has_capabilities(self) -> bool:
        return bool(self.records)

    async def _load_items(self, command):
        self.records = [SimpleNamespace(**item.data) for item in command.items]
        return SimpleNamespace(loaded=len(self.records))

    async def _list_capabilities(self):
        return list(self.records)


async def _load_seed_records(test_session) -> list[SimpleNamespace]:
    dataservice = _SeedCatalogFake()
    loader = CapabilityLoader(session=test_session, dataservice=dataservice)
    n = await loader.load_seeds_if_empty()
    assert n >= 5, f"expected at least 5 thesis capabilities, loaded {n}"
    return dataservice.records


@pytest.mark.asyncio
async def test_thesis_seeds_load(test_session):
    """All thesis YAML seeds load into the DataService catalog contract."""
    records = await _load_seed_records(test_session)

    by_key = {(record.workspace_type, record.id): record for record in records}
    expected_ids = [
        "deep_research",
        "outline_generate",
        "section_write",
        "section_revise",
        "opening_research",
    ]
    for cap_id in expected_ids:
        cap = by_key.get(("thesis", cap_id))
        assert cap is not None, f"capability '{cap_id}' not loaded"
        assert cap.brief_schema, f"capability '{cap_id}' has empty brief_schema"
        assert cap.graph_template, f"capability '{cap_id}' has empty graph_template"
        assert cap.display_name, f"capability '{cap_id}' has empty display_name"


@pytest.mark.asyncio
async def test_seeds_use_only_registered_subagents(test_session):
    """Every subagent_type referenced in seeds must be in REGISTRY."""
    import src.subagents.v2.types  # noqa: F401
    from src.subagents.v2.registry import REGISTRY

    records = await _load_seed_records(test_session)
    thesis_caps = [record for record in records if record.workspace_type == "thesis"]
    assert len(thesis_caps) >= 5, "Expected at least 5 thesis capabilities"

    registered = set(REGISTRY.all_names())
    expected_v1_subagents = {"searcher", "react"}
    missing = expected_v1_subagents - registered
    assert not missing, f"Missing V1 subagents from REGISTRY: {missing}"

    for cap in thesis_caps:
        for phase in cap.graph_template["phases"]:
            for task in phase["tasks"]:
                sa_type = task["subagent_type"]
                assert sa_type in registered, (
                    f"Capability '{cap.id}' phase '{phase['name']}' task "
                    f"'{task['name']}' references unregistered subagent '{sa_type}'. "
                    f"Registered: {sorted(registered)}"
                )


@pytest.mark.asyncio
async def test_seeds_idempotent(test_session):
    """Calling load_seeds_if_empty twice returns 0 on the second call."""
    dataservice = _SeedCatalogFake()
    loader = CapabilityLoader(session=test_session, dataservice=dataservice)

    n1 = await loader.load_seeds_if_empty()
    assert n1 >= 5

    n2 = await loader.load_seeds_if_empty()
    assert n2 == 0, "Second call should be a no-op (catalog already populated)"


@pytest.mark.asyncio
async def test_seeds_have_trigger_phrases(test_session):
    """Each thesis seed must declare at least 1 trigger phrase."""
    records = await _load_seed_records(test_session)

    for cap in [record for record in records if record.workspace_type == "thesis"]:
        assert isinstance(cap.trigger_phrases, list), (
            f"'{cap.id}' trigger_phrases is not a list"
        )
        assert len(cap.trigger_phrases) >= 1, (
            f"'{cap.id}' has no trigger phrases — at least 1 required"
        )
