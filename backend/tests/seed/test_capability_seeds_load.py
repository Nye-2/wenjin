"""Tests for Task 2.13: 5 V1 thesis capability seeds.

Verifies that all 5 seed YAMLs:
1. Load and insert successfully into a fresh DB.
2. Reference only subagent types registered in REGISTRY.

Spec: docs/superpowers/specs/2026-05-09-wenjin-workspace-rebuild-design.md §4.3.3
Plan: docs/superpowers/plans/2026-05-09-wenjin-workspace-rebuild.md Task 2.13
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.services.capability_loader import CapabilityLoader
from tests.database.conftest import DbCapability

# ---------------------------------------------------------------------------
# Test 1: All 5 thesis seeds load + are queryable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thesis_seeds_load(test_session):
    """All 5 thesis YAMLs load + insert into DB successfully."""
    loader = CapabilityLoader(
        session=test_session,
        model=DbCapability,
        # Default seed_dir resolves to backend/seed/capabilities — uses real seeds
    )
    n = await loader.load_seeds_if_empty()
    assert n >= 5, f"expected at least 5 thesis capabilities, loaded {n}"

    # Verify all 5 specific IDs are present and have required fields
    expected_ids = [
        "deep_research",
        "outline_generate",
        "section_write",
        "section_revise",
        "opening_research",
    ]
    for cap_id in expected_ids:
        result = await test_session.execute(
            select(DbCapability).where(
                DbCapability.id == cap_id,
                DbCapability.workspace_type == "thesis",
            )
        )
        cap = result.scalars().first()
        assert cap is not None, f"capability '{cap_id}' not loaded"
        assert cap.brief_schema, f"capability '{cap_id}' has empty brief_schema"
        assert cap.graph_template, f"capability '{cap_id}' has empty graph_template"
        assert cap.display_name, f"capability '{cap_id}' has empty display_name"


# ---------------------------------------------------------------------------
# Test 2: Seeds use only registered subagent types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seeds_use_only_registered_subagents(test_session):
    """Every subagent_type referenced in seeds must be in REGISTRY."""
    # Force imports so @subagent decorators populate REGISTRY
    import src.subagents.v2.types  # noqa: F401
    from src.subagents.v2.registry import REGISTRY

    loader = CapabilityLoader(
        session=test_session,
        model=DbCapability,
    )
    await loader.load_seeds_if_empty()

    result = await test_session.execute(
        select(DbCapability).where(DbCapability.workspace_type == "thesis")
    )
    caps = result.scalars().all()
    assert len(caps) >= 5, "Expected at least 5 thesis capabilities"

    registered = set(REGISTRY.all_names())
    # The 5 V1 subagents must all be registered (other test-only agents may also be
    # present from prior tests in the same session — that's fine, we don't enforce
    # exact count, just that production subagents exist + seeds reference only known ones).
    expected_v1_subagents = {"searcher", "react"}
    missing = expected_v1_subagents - registered
    assert not missing, f"Missing V1 subagents from REGISTRY: {missing}"

    for cap in caps:
        for phase in cap.graph_template["phases"]:
            for task in phase["tasks"]:
                sa_type = task["subagent_type"]
                assert sa_type in registered, (
                    f"Capability '{cap.id}' phase '{phase['name']}' task "
                    f"'{task['name']}' references unregistered subagent '{sa_type}'. "
                    f"Registered: {sorted(registered)}"
                )


# ---------------------------------------------------------------------------
# Test 3: Loader is idempotent (skips when DB already has data)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seeds_idempotent(test_session):
    """Calling load_seeds_if_empty twice returns 0 on the second call."""
    loader = CapabilityLoader(session=test_session, model=DbCapability)

    n1 = await loader.load_seeds_if_empty()
    assert n1 >= 5

    n2 = await loader.load_seeds_if_empty()
    assert n2 == 0, "Second call should be a no-op (DB already populated)"


# ---------------------------------------------------------------------------
# Test 4: Each seed has non-empty trigger_phrases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seeds_have_trigger_phrases(test_session):
    """Each thesis seed must declare at least 1 trigger phrase."""
    loader = CapabilityLoader(session=test_session, model=DbCapability)
    await loader.load_seeds_if_empty()

    result = await test_session.execute(
        select(DbCapability).where(DbCapability.workspace_type == "thesis")
    )
    caps = result.scalars().all()

    for cap in caps:
        assert isinstance(cap.trigger_phrases, list), (
            f"'{cap.id}' trigger_phrases is not a list"
        )
        assert len(cap.trigger_phrases) >= 1, (
            f"'{cap.id}' has no trigger phrases — at least 1 required"
        )
