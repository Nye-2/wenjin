"""Tests for SkillResolver catalog lookup with cache invalidation."""

from types import SimpleNamespace

import pytest

from src.services.skill_resolver import SkillResolver


class _FakeSkillCatalog:
    def __init__(self, skills):
        self.skills = {skill.id: skill for skill in skills}

    async def get_catalog_skill(self, skill_id: str):
        return self.skills.get(skill_id)

    async def list_catalog_skills(self, *, enabled_only: bool = False):
        return [
            skill
            for skill in self.skills.values()
            if not enabled_only or skill.enabled
        ]


def _skill(skill_id: str, *, enabled: bool = True):
    return SimpleNamespace(
        id=skill_id,
        enabled=enabled,
        display_name=skill_id,
        description="x",
        subagent_type="react",
        prompt="写综述",
        allowed_tools=[],
        resources=[],
        config={"output_kind": "document"},
    )


@pytest.mark.asyncio
async def test_resolve_returns_cached_skill() -> None:
    resolver = SkillResolver(
        session_factory=lambda: None,
        dataservice=_FakeSkillCatalog([_skill("literature-reviewer")]),
    )

    skill1 = await resolver.resolve("literature-reviewer")
    assert skill1 is not None
    assert skill1.prompt == "写综述"

    skill2 = await resolver.resolve("literature-reviewer")
    assert skill2 is skill1


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown() -> None:
    resolver = SkillResolver(
        session_factory=lambda: None,
        dataservice=_FakeSkillCatalog([]),
    )
    result = await resolver.resolve("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_list_all_enabled() -> None:
    resolver = SkillResolver(
        session_factory=lambda: None,
        dataservice=_FakeSkillCatalog([
            _skill("a"),
            _skill("b", enabled=False),
        ]),
    )
    skills = await resolver.list_all_enabled()
    assert {skill.id for skill in skills} == {"a"}


@pytest.mark.asyncio
async def test_on_invalidate_clears_cache() -> None:
    resolver = SkillResolver(
        session_factory=lambda: None,
        dataservice=_FakeSkillCatalog([_skill("x")]),
    )
    skill = await resolver.resolve("x")
    assert skill is not None
    assert skill.id == "x"

    await resolver._on_invalidate({"skill_id": "x"})
    assert "x" not in resolver._cache

    refreshed = await resolver.resolve("x")
    assert refreshed is not None
    assert refreshed.id == "x"
