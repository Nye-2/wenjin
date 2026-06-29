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
        records = []
        for item in command.items:
            data = dict(item.data)
            data.setdefault("definition_json", dict(item.data))
            records.append(SimpleNamespace(**data))
        self.records = records
        return SimpleNamespace(loaded=len(self.records))

    async def _list_capabilities(self):
        return list(self.records)


async def _load_seed_records() -> list[SimpleNamespace]:
    dataservice = _SeedCatalogFake()
    loader = CapabilityLoader(dataservice=dataservice)
    n = await loader.load_seeds_if_empty()
    assert n >= 6, f"expected mission capabilities, loaded {n}"
    return dataservice.records


@pytest.mark.asyncio
async def test_thesis_seeds_load():
    """All thesis YAML seeds load into the DataService catalog contract."""
    records = await _load_seed_records()

    by_key = {(record.workspace_type, record.id): record for record in records}
    expected_ids = [
        "idea_to_thesis_manuscript",
        "thesis_research_pack",
        "thesis_empirical_analysis",
        "thesis_revision_pass",
        "thesis_defense_pack",
        "thesis_reference_curation",
    ]
    for cap_id in expected_ids:
        cap = by_key.get(("thesis", cap_id))
        assert cap is not None, f"capability '{cap_id}' not loaded"
        assert cap.schema_version == "capability.v2"
        assert cap.brief_schema, f"capability '{cap_id}' has empty brief_schema"
        assert cap.graph_template, f"capability '{cap_id}' has empty graph_template"
        assert cap.display_name, f"capability '{cap_id}' has empty display_name"
        assert cap.definition_json["mission"]["primary_surface"] == "prism"


@pytest.mark.asyncio
async def test_seeds_use_only_registered_subagents():
    """Every subagent_type referenced in seeds must be in REGISTRY."""
    import src.subagents.v2.types  # noqa: F401
    from src.subagents.v2.registry import REGISTRY

    records = await _load_seed_records()
    thesis_caps = [record for record in records if record.workspace_type == "thesis"]
    assert len(thesis_caps) >= 6, "Expected at least 6 thesis mission capabilities"

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
async def test_seeds_idempotent():
    """Calling load_seeds_if_empty twice returns 0 on the second call."""
    dataservice = _SeedCatalogFake()
    loader = CapabilityLoader(dataservice=dataservice)

    n1 = await loader.load_seeds_if_empty()
    assert n1 >= 6

    n2 = await loader.load_seeds_if_empty()
    assert n2 == 0, "Second call should be a no-op (catalog already populated)"


@pytest.mark.asyncio
async def test_seeds_have_trigger_phrases():
    """Each thesis seed must declare at least 1 trigger phrase."""
    records = await _load_seed_records()

    for cap in [record for record in records if record.workspace_type == "thesis"]:
        assert isinstance(cap.trigger_phrases, list), (
            f"'{cap.id}' trigger_phrases is not a list"
        )
        assert len(cap.trigger_phrases) >= 1, (
            f"'{cap.id}' has no trigger phrases — at least 1 required"
        )


@pytest.mark.asyncio
async def test_visible_seeds_have_routing_contracts():
    """User-visible capabilities must declare Chat Agent routing guidance."""
    records = await _load_seed_records()

    for cap in records:
        display = cap.definition_json.get("display") or {}
        if not cap.enabled or display.get("entry_tier") == "hidden":
            continue

        routing = cap.definition_json.get("routing")
        assert isinstance(routing, dict), f"'{cap.id}' is missing routing"
        assert routing.get("when_to_use"), f"'{cap.id}' routing.when_to_use is empty"
        assert routing.get("not_for"), f"'{cap.id}' routing.not_for is empty"
        assert routing.get("positive_examples"), (
            f"'{cap.id}' routing.positive_examples is empty"
        )
        assert routing.get("negative_examples"), (
            f"'{cap.id}' routing.negative_examples is empty"
        )
        minimum_context = routing.get("minimum_context")
        assert isinstance(minimum_context, dict) and minimum_context, (
            f"'{cap.id}' routing.minimum_context is empty"
        )


@pytest.mark.asyncio
async def test_one_shot_template_pack_capabilities_load_with_authoritative_extensions():
    records = await _load_seed_records()
    by_key = {(record.workspace_type, record.id): record for record in records}

    expected = {
        ("software_copyright", "software_copyright_application_pack"): {
            "authoritative_template_id": "software_copyright_cn_application_pack",
            "visual_profile_id": "software_copyright_cn_default",
        },
        ("math_modeling", "math_modeling_paper_pack"): {
            "authoritative_template_id": "math_modeling_cumcm2026_paper_pack",
            "visual_profile_id": "math_modeling_cumcm_default",
        },
    }
    for key, expected_extensions in expected.items():
        cap = by_key.get(key)
        assert cap is not None, f"capability '{key}' not loaded"
        assert cap.schema_version == "capability.v2"
        extensions = cap.definition_json.get("extensions") or {}
        for extension_key, expected_value in expected_extensions.items():
            assert extensions.get(extension_key) == expected_value


@pytest.mark.asyncio
async def test_old_workflow_ids_not_loaded():
    records = await _load_seed_records()
    old_ids = {
        "deep_research",
        "outline_generate",
        "section_write",
        "section_revise",
        "opening_research",
        "framework_outline",
        "section_writing",
        "proposal_outline",
        "patent_outline",
        "figure_generation",
        "writing",
        "thesis_writing",
    }
    current_ids = {record.id for record in records}
    assert old_ids.isdisjoint(current_ids)
