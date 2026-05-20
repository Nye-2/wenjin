"""Tests for SkillResolver — runtime DB lookup with cache invalidation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.skill_resolver import SkillResolver
from tests.unit.conftest import UnitCapabilitySkill


@pytest.mark.asyncio
async def test_resolve_returns_cached_skill(db_session: AsyncSession) -> None:
    db_session.add(UnitCapabilitySkill(
        id="literature-reviewer",
        display_name="文献综述写手",
        description="x",
        subagent_type="react",
        prompt="写综述",
        allowed_tools=[],
        resources=[],
        config={"output_kind": "document"},
    ))
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skill1 = await resolver.resolve("literature-reviewer")
    assert skill1 is not None
    assert skill1.prompt == "写综述"

    # Second call returns same object from cache
    skill2 = await resolver.resolve("literature-reviewer")
    assert skill2 is skill1


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown(db_session: AsyncSession) -> None:
    resolver = SkillResolver(session_factory=lambda: db_session)
    result = await resolver.resolve("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_list_all_enabled(db_session: AsyncSession) -> None:
    db_session.add_all([
        UnitCapabilitySkill(id="a", display_name="A", subagent_type="react", enabled=True),
        UnitCapabilitySkill(id="b", display_name="B", subagent_type="react", enabled=False),
    ])
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skills = await resolver.list_all_enabled()
    assert {s.id for s in skills} == {"a"}


@pytest.mark.asyncio
async def test_on_invalidate_clears_cache(db_session: AsyncSession) -> None:
    db_session.add(UnitCapabilitySkill(id="x", display_name="X", subagent_type="react", prompt="v1"))
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skill = await resolver.resolve("x")
    assert skill is not None
    assert skill.id == "x"

    # Invalidate clears cache entry
    await resolver._on_invalidate({"skill_id": "x"})
    assert "x" not in resolver._cache

    # Re-resolve returns fresh data
    refreshed = await resolver.resolve("x")
    assert refreshed is not None
    assert refreshed.id == "x"
