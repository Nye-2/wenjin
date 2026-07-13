"""worker_skill.v1 loader tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from src.contracts.mission_policy import WorkerSkill
from src.services.skill_loader import SkillLoader


def _payload(skill_id: str = "research-scout") -> dict:
    return {
        "schema_version": "worker_skill.v1",
        "id": skill_id,
        "version": 1,
        "enabled": True,
        "role_hint": "Source scout",
        "instructions": ["Find verifiable sources.", "Never invent metadata."],
        "allowed_tool_groups": ["model_native_web_search"],
        "input_contract": {"type": "object"},
        "output_contract": {
            "type": "object",
            "required": ["summary", "evidence_refs", "artifact_refs", "warnings"],
        },
        "quality_focus": ["source identity"],
        "examples": [
            {
                "task": "Find sources",
                "strong_output_characteristics": ["stable refs"],
            }
        ],
    }


class _CatalogFake:
    def __init__(self) -> None:
        self.has_worker_skills = AsyncMock(return_value=False)
        self.load_worker_skill_seed_items = AsyncMock(return_value=SimpleNamespace(loaded=1))
        self.list_worker_skills = AsyncMock(return_value=[])


@pytest.mark.asyncio
async def test_loads_bounded_worker_skill(tmp_path) -> None:
    path = tmp_path / "research-scout.yaml"
    path.write_text(yaml.safe_dump(_payload(), sort_keys=False))
    dataservice = _CatalogFake()

    count = await SkillLoader(seed_dir=tmp_path, dataservice=dataservice).load_seeds_if_empty()

    assert count == 1
    item = dataservice.load_worker_skill_seed_items.await_args.args[0].items[0]
    assert item.data["schema_version"] == "worker_skill.v1"
    assert item.data["content_hash"] == WorkerSkill.model_validate(_payload()).immutable_ref().sha256
    assert item.source_path == "research-scout.yaml"
    assert "role_prompt" not in item.data
    assert "quality_gates" not in item.data


def test_skill_updates_are_independent_of_host_absolute_path(tmp_path) -> None:
    (tmp_path / "research-scout.yaml").write_text(yaml.safe_dump(_payload(), sort_keys=False))
    loader = SkillLoader(seed_dir=tmp_path)
    item = loader.read_seed_items()[0]
    existing = SimpleNamespace(
        id=item["data"]["id"],
        source_path="/another-host/app/seed/skills/research-scout.yaml",
        content_hash=item["data"]["content_hash"],
    )

    updates = loader.select_seed_updates([existing])

    assert updates[0]["source_path"] == "research-scout.yaml"


def test_rejects_old_skill_schema(tmp_path) -> None:
    (tmp_path / "old.yaml").write_text("schema_version: capability_skill.v2\nid: old\n")

    with pytest.raises(ValueError, match="worker_skill.v1"):
        SkillLoader(seed_dir=tmp_path).read_seed_items()


def test_rejects_unbounded_instruction_pack(tmp_path) -> None:
    payload = _payload()
    payload["instructions"] = ["rule"] * 13
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match="1 to 12"):
        SkillLoader(seed_dir=tmp_path).read_seed_items()
