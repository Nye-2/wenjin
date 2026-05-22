"""Tests for CapabilityResolver and validate_capability."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _make_event_bus():
    """Create a mock EventBus that tracks subscribed handlers."""
    bus = AsyncMock()
    bus._handlers = {}

    def _subscribe(channel, handler):
        bus._handlers.setdefault(channel, []).append(handler)

    bus.subscribe = _subscribe
    return bus


def _capability(**overrides):
    defaults = {
        "id": "deep_research",
        "workspace_type": "thesis",
        "display_name": "深度文献调研",
        "enabled": True,
        "intent_description": "用户希望对某个主题做学术性的深度文献调研",
        "brief_schema": {
            "type": "object",
            "required": ["topic"],
            "properties": {"topic": {"type": "string"}},
        },
        "graph_template": {
            "phases": [
                {
                    "name": "discover",
                    "tasks": [
                        {"name": "search", "subagent_type": "searcher"}
                    ],
                },
                {
                    "name": "synthesize",
                    "depends_on": ["discover"],
                    "tasks": [
                        {"name": "write", "subagent_type": "react"}
                    ],
                },
            ]
        },
        "ui_meta": {"icon": "search", "color": "purple", "order": 0},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeCapabilityCatalog:
    def __init__(self, capabilities):
        self.capabilities = {
            (cap.workspace_type, cap.id): cap
            for cap in capabilities
        }

    async def get_catalog_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = True,
    ):
        cap = self.capabilities.get((workspace_type, capability_id))
        if cap is None:
            return None
        if enabled_only and not cap.enabled:
            return None
        return cap

    async def list_catalog_capabilities(
        self,
        *,
        workspace_type: str,
        enabled_only: bool = True,
    ):
        return [
            cap
            for cap in self.capabilities.values()
            if cap.workspace_type == workspace_type
            and (not enabled_only or cap.enabled)
        ]


@pytest.mark.asyncio
async def test_resolve_from_dataservice_catalog():
    """Seed capability → resolve → returns correct Capability."""
    from src.services.capability_resolver import CapabilityResolver

    bus = _make_event_bus()
    resolver = CapabilityResolver(
        session_factory=lambda: None,
        event_bus=bus,
        dataservice=_FakeCapabilityCatalog([_capability()]),
    )

    cap = await resolver.resolve("deep_research", "thesis")

    assert cap.id == "deep_research"
    assert cap.workspace_type == "thesis"
    assert cap.display_name == "深度文献调研"


@pytest.mark.asyncio
async def test_resolve_uses_cache():
    """Resolve twice → same object reference (cache hit)."""
    from src.services.capability_resolver import CapabilityResolver

    bus = _make_event_bus()
    resolver = CapabilityResolver(
        session_factory=lambda: None,
        event_bus=bus,
        dataservice=_FakeCapabilityCatalog([_capability()]),
    )

    cap1 = await resolver.resolve("deep_research", "thesis")
    cap2 = await resolver.resolve("deep_research", "thesis")

    assert cap1 is cap2  # Same object reference = cache hit


@pytest.mark.asyncio
async def test_invalidate_clears_cache():
    """Resolve → publish invalidate event → cache entry removed → catalog re-read."""
    from src.services.capability_resolver import CapabilityResolver

    bus = _make_event_bus()
    resolver = CapabilityResolver(
        session_factory=lambda: None,
        event_bus=bus,
        dataservice=_FakeCapabilityCatalog([_capability()]),
    )

    cap1 = await resolver.resolve("deep_research", "thesis")
    assert ("deep_research", "thesis") in resolver._cache

    # Simulate invalidation event
    invalidate_handler = bus._handlers["capability.invalidated"][0]
    await invalidate_handler({
        "id": "deep_research",
        "workspace_type": "thesis",
    })

    # Cache entry should be removed
    assert ("deep_research", "thesis") not in resolver._cache

    # Resolve again — DB re-queried (same data, since same session identity map)
    cap2 = await resolver.resolve("deep_research", "thesis")
    assert cap2.id == cap1.id


@pytest.mark.asyncio
async def test_validate_capability_good():
    """Valid data → empty errors."""
    from src.services.capability_resolver import validate_capability

    data = {
        "brief_schema": {
            "type": "object",
            "required": ["topic"],
            "properties": {"topic": {"type": "string"}},
        },
        "graph_template": {
            "phases": [
                {
                    "name": "discover",
                    "tasks": [
                        {
                            "name": "search",
                            "subagent_type": "searcher",
                            "prompt_template": "搜索关于 {{topic}} 的文献",
                        }
                    ],
                },
                {
                    "name": "synthesize",
                    "depends_on": ["discover"],
                    "tasks": [
                        {
                            "name": "write",
                            "subagent_type": "react",
                            "prompt_template": "写综述 {{topic}}",
                        }
                    ],
                },
            ]
        },
        "system_prompt": "你是学术文献调研专家。关于 {{topic}} 的调研。",
    }

    errors = validate_capability(data, subagent_registry=["searcher", "react"])
    assert errors == []


@pytest.mark.asyncio
async def test_validate_capability_bad_depends_on():
    """Phase depends on nonexistent → error string returned."""
    from src.services.capability_resolver import validate_capability

    data = {
        "brief_schema": {"type": "object", "properties": {}},
        "graph_template": {
            "phases": [
                {"name": "discover", "tasks": []},
                {
                    "name": "synthesize",
                    "depends_on": ["nonexistent_phase"],
                    "tasks": [],
                },
            ]
        },
        "system_prompt": "test",
    }

    errors = validate_capability(data)
    assert len(errors) == 1
    assert "nonexistent_phase" in errors[0]
    assert "depends_on" in errors[0]
