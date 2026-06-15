"""DataService catalog domain tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.catalog.projection import skill_to_record
from src.dataservice.domains.catalog.seed_loader import DataServiceCatalogSeedLoader
from src.dataservice.domains.catalog.service import DataServiceCatalogService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


class FakeCatalogRepository:
    def __init__(self) -> None:
        self.capability_values: dict[str, Any] | None = None
        self.skill_values: dict[str, Any] | None = None
        self.agent_template_values: dict[str, Any] | None = None
        self.latest = None

    async def upsert_capability(self, values: dict[str, Any]):
        self.capability_values = values
        return SimpleNamespace(created_at=None, updated_at=None, **values)

    async def upsert_skill(self, values: dict[str, Any]):
        self.skill_values = values
        return SimpleNamespace(**values)

    async def upsert_agent_template(self, values: dict[str, Any]):
        self.agent_template_values = values
        return SimpleNamespace(created_at=None, updated_at=None, **values)

    async def latest_seed_revision(self, *, catalog_kind: str, seed_root: str):
        return self.latest

    def create_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
        loaded_count: int,
        metadata_json: dict[str, Any],
    ):
        self.latest = SimpleNamespace(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
            loaded_count=loaded_count,
            metadata_json=metadata_json,
        )
        return self.latest


def _service() -> tuple[DataServiceCatalogService, FakeCatalogRepository, FakeSession]:
    session = FakeSession()
    service = DataServiceCatalogService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeCatalogRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def _capability_v2_data() -> dict[str, Any]:
    return {
        "schema_version": "capability.v2",
        "id": "idea_to_thesis_manuscript",
        "workspace_type": "thesis",
        "enabled": True,
        "display": {
            "name": "从想法到全文",
            "description": "根据确定的 idea 完成全文写作",
            "icon": "file-pen",
            "color": "blue",
            "order": 10,
            "entry_tier": "primary",
        },
        "intent": {
            "description": "根据确定的 idea 完成全文写作",
            "trigger_phrases": ["写全文"],
        },
        "mission": {
            "goal": "produce_or_update_primary_document",
            "primary_surface": "prism",
            "document_role": "primary_manuscript",
            "user_promise": "生成可审阅的主文档变更",
            "allowed_deliverables": ["full_document_update"],
        },
        "inputs": {
            "required_decisions": [],
            "brief_schema": {"type": "object"},
        },
        "context_policy": {
            "room_reads": {},
            "prism_context": {},
            "full_text_access": "explicit_tool_only",
        },
        "sandbox_policy": {
            "mode": "conditional",
            "profiles": ["analysis"],
            "allowed_operations": ["run_python"],
        },
        "review_policy": {
            "default_targets": ["prism_file_change"],
            "require_user_acceptance": True,
            "allow_bulk_accept": True,
        },
        "quality_gates": ["no_direct_primary_document_write"],
        "graph_template": {"phases": []},
        "ui_meta": {
            "icon": "file-pen",
            "color": "blue",
            "order": 10,
            "entry_tier": "primary",
            "stages": [],
        },
        "runtime": {
            "mode": "compute_agentic",
            "sandbox_policy": {
                "mode": "conditional",
                "profiles": ["analysis"],
                "allowed_operations": ["run_python"],
            },
        },
        "dashboard_meta": {},
    }


def _routing_contract() -> dict[str, Any]:
    return {
        "when_to_use": ["用户需要整理文献、gap 和创新点"],
        "not_for": ["概念解释", "单句润色", "直接写论文全文"],
        "user_intents": ["找研究空白"],
        "positive_examples": [
            "联邦学习结合大模型有什么创新点？",
            "帮我整理这个方向的研究空白",
            "围绕隐私计算找可发表的创新点",
        ],
        "negative_examples": [
            "联邦学习是什么？",
            "帮我把这句话润色一下",
            "直接根据这个题目写论文全文",
        ],
        "minimum_context": {"goal_or_topic": "required"},
        "clarification": {
            "ask_when_missing": {
                "goal_or_topic": "你想聚焦哪个具体主题？",
            },
        },
        "user_guidance": {
            "launch_intro": "我会让文献专家先整理相关工作、gap 和可用论断。",
        },
    }


def _skill_v2_data() -> dict[str, Any]:
    return {
        "schema_version": "capability_skill.v2",
        "id": "manuscript-writer",
        "enabled": True,
        "display_name": "全文写手",
        "description": "生成可进入 Prism review 的主文档正文变更",
        "worker": {
            "category": "writing",
            "subagent_type": "react",
            "role_prompt": "write",
        },
        "io_contract": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
        "context_access": {
            "room_reads": {},
            "prism_context": "lightweight",
        },
        "tool_policy": {"allowed_tools": []},
        "sandbox_access": {"mode": "none", "profiles": []},
        "quality_gates": ["no_direct_primary_document_write"],
    }


def _agent_template_data() -> dict[str, Any]:
    return {
        "schema_version": "agent_template.v1",
        "id": "research_scout.v1",
        "enabled": True,
        "display_role": "文献检索员",
        "category": "research",
        "description": "检索、筛选、记录来源。",
        "persona_prompt": "You are a research scout.",
        "default_skills": ["research-scout"],
        "tool_affinity": {"preferred": ["web_search"], "can_request": ["library_read"]},
        "risk_profile": {"room_write": "staged_only"},
        "output_contracts": ["literature_source_log.v1"],
        "quality_expectations": ["accepted sources must map to claims"],
        "runtime_defaults": {"max_turns": 8},
        "expert_profile": {
            "public_name": "文献猎手 Nora",
            "short_name": "文献猎手",
            "role_title": "文献检索专家",
            "avatar_label": "文",
            "tone": "witty_professional",
            "status_phrases": {"running": "扫文献雷达中"},
        },
    }


def test_skill_projection_requires_canonical_skill_json() -> None:
    skill = SimpleNamespace(
        id="writer",
        schema_version="capability_skill.v2",
        enabled=True,
        display_name="Writer",
        description="",
        worker_type="writer",
        subagent_type="react",
        prompt="write",
        allowed_tools=[],
        resources=[],
        config={},
        skill_json={},
        checksum=None,
        source_path=None,
    )

    with pytest.raises(ValueError, match="canonical skill_json"):
        skill_to_record(skill)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_upsert_capability_materializes_v2_definition_json() -> None:
    service, repository, session = _service()
    data = _capability_v2_data()
    data["routing"] = _routing_contract()

    record = await service.upsert_capability(
        data,
        checksum="abc",
        source_path="seed.yaml",
    )

    assert record.schema_version == "capability.v2"
    assert record.tier == "primary"
    assert record.entry_surface == "workbench"
    assert record.definition_json["schema_version"] == "capability.v2"
    assert record.definition_json["routing"]["user_intents"] == ["找研究空白"]
    assert record.routing["when_to_use"] == ["用户需要整理文献、gap 和创新点"]
    assert record.routing["minimum_context"]["goal_or_topic"] == "required"
    assert record.display_name == "从想法到全文"
    assert record.checksum == "abc"
    assert repository.capability_values is not None
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upsert_skill_materializes_worker_type_and_skill_json() -> None:
    service, repository, session = _service()

    record = await service.upsert_skill(
        _skill_v2_data()
    )

    assert record.schema_version == "capability_skill.v2"
    assert record.worker_type == "writing"
    assert record.skill_json["worker_type"] == "writing"
    assert repository.skill_values is not None
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upsert_agent_template_materializes_expert_profile() -> None:
    service, repository, session = _service()

    record = await service.upsert_agent_template(
        _agent_template_data(),
        checksum="agent-checksum",
        source_path="agent_templates/research_scout.yaml",
    )

    assert record.expert_profile["schema_version"] == "wenjin.team.expert_profile.v1"
    assert record.expert_profile["public_name"] == "文献猎手 Nora"
    assert record.template_json["expert_profile"]["status_phrases"]["running"] == "扫文献雷达中"
    assert repository.agent_template_values is not None
    assert session.commit_count == 1


def test_agent_template_values_reject_invalid_expert_profile() -> None:
    data = _agent_template_data()
    data["expert_profile"] = {
        "public_name": "文献猎手 Nora",
        "role_title": "文献检索专家",
        "status_phrases": {"sleeping": "zzz"},
    }

    with pytest.raises(ValueError, match="expert_profile"):
        DataServiceCatalogService.agent_template_values(data)


@pytest.mark.asyncio
async def test_seed_revision_is_idempotent_by_checksum() -> None:
    service, repository, session = _service()

    first = await service.record_seed_revision(
        catalog_kind="capabilities",
        seed_root="/seed/capabilities",
        checksum="same",
        loaded_count=2,
    )
    second = await service.record_seed_revision(
        catalog_kind="capabilities",
        seed_root="/seed/capabilities",
        checksum="same",
        loaded_count=2,
    )

    assert first.loaded == 2
    assert first.skipped is False
    assert second.loaded == 0
    assert second.skipped is True
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_seed_loader_applies_capability_revision_once(tmp_path) -> None:
    service, repository, session = _service()
    seed_dir = tmp_path / "capabilities"
    workspace_dir = seed_dir / "thesis"
    workspace_dir.mkdir(parents=True)
    seed_file = workspace_dir / "idea_to_thesis.yaml"
    seed_file.write_text("id: idea_to_thesis_manuscript\n", encoding="utf-8")

    def validate(path, text):
        assert path == seed_file
        assert "idea_to_thesis_manuscript" in text
        return {
            **_capability_v2_data(),
        }

    result = await DataServiceCatalogSeedLoader(service, seed_dir).load_capabilities(
        validate_yaml_text=validate,
    )

    assert result.loaded == 1
    assert result.skipped is False
    assert result.checksum
    assert repository.capability_values is not None
    assert repository.capability_values["source_path"] == str(seed_file)
    assert repository.latest.metadata_json["schema_version"] == "capability.v2"
    assert session.commit_count == 1
