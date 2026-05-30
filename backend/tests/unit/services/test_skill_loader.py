"""Tests for SkillLoader — YAML → DB seed loader."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from src.services.skill_loader import SkillLoader


class _SkillSeedCatalogFake:
    def __init__(self, *, has_skills: bool = False) -> None:
        self.has_catalog_skills = AsyncMock(return_value=has_skills)
        self.load_catalog_skill_seed_items = AsyncMock()
        self.list_catalog_skills = AsyncMock(return_value=[])


def _skill_v2_payload(*, skill_id: str = "research-scout") -> dict:
    return {
        "schema_version": "capability_skill.v2",
        "id": skill_id,
        "enabled": True,
        "display_name": "Research Scout",
        "description": "建立材料池、检索、筛选和摘要",
        "worker": {
            "category": "research",
            "subagent_type": "searcher",
            "role_prompt": "Search and summarize relevant sources.",
        },
        "io_contract": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
        "context_access": {
            "room_reads": {"library": "summary"},
            "prism_context": "summary",
        },
        "tool_policy": {"allowed_tools": []},
        "sandbox_access": {"mode": "none", "profiles": []},
        "quality_gates": ["source_quality_checked"],
    }


@pytest.mark.asyncio
async def test_load_seeds_if_empty_inserts_all_yamls(tmp_path: Path) -> None:
    skill_yaml = tmp_path / "scholar-searcher.yaml"
    skill_yaml.write_text(yaml.safe_dump(_skill_v2_payload(skill_id="research-scout")))

    dataservice = _SkillSeedCatalogFake(has_skills=False)
    dataservice.load_catalog_skill_seed_items.return_value.loaded = 1
    loader = SkillLoader(seed_dir=tmp_path, dataservice=dataservice)
    count = await loader.load_seeds_if_empty()
    assert count == 1

    command = dataservice.load_catalog_skill_seed_items.await_args.args[0]
    assert command.items[0].data["schema_version"] == "capability_skill.v2"
    assert command.items[0].data["id"] == "research-scout"
    assert command.items[0].data["worker_type"] == "research"
    assert command.items[0].data["subagent_type"] == "searcher"
    assert command.items[0].data["config"]["quality_gates"] == ["source_quality_checked"]


@pytest.mark.asyncio
async def test_load_seeds_if_empty_skips_when_populated(tmp_path: Path) -> None:
    skill_yaml = tmp_path / "new.yaml"
    skill_yaml.write_text(yaml.safe_dump(_skill_v2_payload(skill_id="new")))

    dataservice = _SkillSeedCatalogFake(has_skills=True)
    loader = SkillLoader(seed_dir=tmp_path, dataservice=dataservice)
    count = await loader.load_seeds_if_empty()
    assert count == 0
    dataservice.load_catalog_skill_seed_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_dataservice_branch_loads_seed_items(tmp_path: Path) -> None:
    skill_yaml = tmp_path / "writer.yaml"
    skill_yaml.write_text(yaml.safe_dump(_skill_v2_payload(skill_id="writer")))
    dataservice = AsyncMock()
    dataservice.has_catalog_skills.return_value = False
    dataservice.load_catalog_skill_seed_items.return_value.loaded = 1
    loader = SkillLoader(seed_dir=tmp_path, dataservice=dataservice)

    count = await loader.load_seeds_if_empty()

    assert count == 1
    command = dataservice.load_catalog_skill_seed_items.await_args.args[0]
    assert command.seed_root == str(tmp_path)
    assert command.items[0].data["id"] == "writer"
    assert command.items[0].source_path == str(skill_yaml)
