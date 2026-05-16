"""Tests for cross-reference validation across capability + skill + registry."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.capability_schema import CrossRefValidator, CapabilityYamlModel


def _make_capability_yaml(
    skill_ids: list[str], subagent_types: list[str]
) -> CapabilityYamlModel:
    return CapabilityYamlModel(
        id="x",
        workspace_type="thesis",
        display_name="X",
        intent_description="x",
        brief_schema={},
        ui_meta={"icon": "x", "color": "x"},
        graph_template={
            "phases": [
                {
                    "name": "p",
                    "tasks": [
                        {"name": f"t{i}", "subagent_type": st, "skill_id": sid}
                        for i, (st, sid) in enumerate(zip(subagent_types, skill_ids))
                    ],
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_skill_id_missing_fails(monkeypatch):
    db = AsyncMock(spec=AsyncSession)

    async def fake_existing_skill_ids(_db, _ids):
        return set()  # no skills exist

    monkeypatch.setattr(
        CrossRefValidator,
        "_existing_skill_ids",
        staticmethod(fake_existing_skill_ids),
    )
    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    cap = _make_capability_yaml(
        skill_ids=["literature-reviewer"], subagent_types=["react"]
    )
    errors = await CrossRefValidator(db).validate_capability(cap)
    assert any("literature-reviewer" in e for e in errors)


@pytest.mark.asyncio
async def test_subagent_type_unknown_fails(monkeypatch):
    db = AsyncMock(spec=AsyncSession)

    async def fake_existing(_db, ids):
        return set(ids)

    monkeypatch.setattr(
        CrossRefValidator,
        "_existing_skill_ids",
        staticmethod(fake_existing),
    )
    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    cap = _make_capability_yaml(
        skill_ids=["any-skill"], subagent_types=["nonexistent"]
    )
    errors = await CrossRefValidator(db).validate_capability(cap)
    assert any("nonexistent" in e for e in errors)


@pytest.mark.asyncio
async def test_skill_subagent_type_validated(monkeypatch):
    from src.services.capability_schema import CapabilitySkillYamlModel

    db = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    skill = CapabilitySkillYamlModel(
        id="x",
        display_name="X",
        subagent_type="bogus",
    )
    errors = await CrossRefValidator(db).validate_skill(skill)
    assert any("bogus" in e for e in errors)
