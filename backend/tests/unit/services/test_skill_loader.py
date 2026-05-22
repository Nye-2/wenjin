"""Tests for SkillLoader — YAML → DB seed loader."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.skill_loader import SkillLoader


class _SkillSeedCatalogFake:
    def __init__(self, *, has_skills: bool = False) -> None:
        self.has_catalog_skills = AsyncMock(return_value=has_skills)
        self.load_catalog_skill_seed_items = AsyncMock()
        self.list_catalog_skills = AsyncMock(return_value=[])


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

    dataservice = _SkillSeedCatalogFake(has_skills=False)
    dataservice.load_catalog_skill_seed_items.return_value.loaded = 1
    loader = SkillLoader(db_session, seed_dir=tmp_path, dataservice=dataservice)
    count = await loader.load_seeds_if_empty()
    assert count == 1

    command = dataservice.load_catalog_skill_seed_items.await_args.args[0]
    assert command.items[0].data["id"] == "scholar-searcher"
    assert command.items[0].data["config"] == {"sources": ["semantic_scholar"]}


@pytest.mark.asyncio
async def test_load_seeds_if_empty_skips_when_populated(db_session: AsyncSession, tmp_path: Path) -> None:
    skill_yaml = tmp_path / "new.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "new",
        "display_name": "new",
        "subagent_type": "react",
    }))

    dataservice = _SkillSeedCatalogFake(has_skills=True)
    loader = SkillLoader(db_session, seed_dir=tmp_path, dataservice=dataservice)
    count = await loader.load_seeds_if_empty()
    assert count == 0
    dataservice.load_catalog_skill_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_dataservice_branch_loads_seed_items(db_session: AsyncSession, tmp_path: Path) -> None:
    skill_yaml = tmp_path / "writer.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "writer",
        "display_name": "Writer",
        "subagent_type": "react",
    }))
    dataservice = AsyncMock()
    dataservice.has_catalog_skills.return_value = False
    dataservice.load_catalog_skill_seed_items.return_value.loaded = 1
    loader = SkillLoader(db_session, seed_dir=tmp_path, dataservice=dataservice)

    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_skill_seed_items.await_args.args[0]
    assert command.seed_root == str(tmp_path)
    assert command.items[0].data["id"] == "writer"
    assert command.items[0].source_path == str(skill_yaml)
