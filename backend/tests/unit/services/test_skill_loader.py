"""Tests for SkillLoader — YAML → DB seed loader."""

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.skill_loader import SkillLoader
from tests.unit.conftest import UnitCapabilitySkill


@pytest.mark.asyncio
async def test_load_seeds_if_empty_inserts_all_yamls(db_session: AsyncSession, tmp_path: Path) -> None:
    skill_yaml = tmp_path / "scholar-searcher.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "scholar-searcher",
        "enabled": True,
        "display_name": "学术文献检索员",
        "description": "调 Semantic Scholar",
        "subagent_type": "searcher",
        "prompt": "(unused)",
        "allowed_tools": [],
        "resources": [],
        "config": {"sources": ["semantic_scholar"]},
    }))

    loader = SkillLoader(db_session, seed_dir=tmp_path, model=UnitCapabilitySkill)
    count = await loader.load_seeds_if_empty()
    assert count == 1

    rows = (await db_session.execute(select(UnitCapabilitySkill))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == "scholar-searcher"
    assert rows[0].config == {"sources": ["semantic_scholar"]}


@pytest.mark.asyncio
async def test_load_seeds_if_empty_skips_when_populated(db_session: AsyncSession, tmp_path: Path) -> None:
    db_session.add(UnitCapabilitySkill(
        id="existing",
        display_name="x",
        description="x",
        subagent_type="react",
        prompt="x",
    ))
    await db_session.commit()

    skill_yaml = tmp_path / "new.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "new",
        "display_name": "new",
        "subagent_type": "react",
    }))

    loader = SkillLoader(db_session, seed_dir=tmp_path, model=UnitCapabilitySkill)
    count = await loader.load_seeds_if_empty()
    assert count == 0
