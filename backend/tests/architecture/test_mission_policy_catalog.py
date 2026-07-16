"""Architecture invariants for the MissionPolicy and WorkerSkill catalog."""

from __future__ import annotations

import inspect

from src.database.models.mission_catalog import MissionPolicyRecord, WorkerSkillRecord
from src.dataservice.domains.catalog.repository import MissionCatalogRepository
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.dataservice_client.catalog_client import CatalogDataServiceClientMixin
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


def _policies() -> list[dict]:
    return [item["data"] for item in MissionPolicyLoader().read_seed_items()]


def _skills() -> list[dict]:
    return [item["data"] for item in SkillLoader().read_seed_items()]


def test_catalog_has_exactly_two_storage_aggregates() -> None:
    assert MissionPolicyRecord.__tablename__ == "mission_policies"
    assert WorkerSkillRecord.__tablename__ == "worker_skills"
    assert {table.name for table in (MissionPolicyRecord.__table__, WorkerSkillRecord.__table__)} == {
        "mission_policies",
        "worker_skills",
    }


def test_catalog_domain_depends_only_on_new_contracts_and_records() -> None:
    source = "\n".join(
        [
            inspect.getsource(MissionCatalogRepository),
            inspect.getsource(MissionCatalogService),
            inspect.getsource(CatalogDataServiceClientMixin),
        ]
    )
    assert "MissionPolicyRecord" in source
    assert "WorkerSkillRecord" in source
    for retired_symbol in (
        "CapabilityDefinition",
        "CapabilitySkill",
        "AgentTemplate",
        "CapabilitySeedRevision",
        "subagents.v2",
    ):
        assert retired_symbol not in source


def test_every_workspace_policy_resolves_only_existing_worker_skills() -> None:
    policies = _policies()
    skill_ids = {skill["id"] for skill in _skills()}

    assert {policy["workspace_type"] for policy in policies} == {
        "sci",
        "thesis",
        "proposal",
        "software_copyright",
        "math_modeling",
        "patent",
    }
    assert len(policies) == 6
    for policy in policies:
        assert policy["schema_version"] == "mission_policy.v1"
        assert set(policy["allowed_worker_skills"]) <= skill_ids
        assert policy["resolved_stage_contracts"]
        assert len(policy["content_hash"]) == 64


def test_worker_skills_are_bounded_guidance_not_hidden_agent_workflows() -> None:
    forbidden = {
        "role_prompt",
        "subagent_type",
        "graph_template",
        "team_policy",
        "quality_gates",
        "runtime_defaults",
    }
    for skill in _skills():
        assert skill["schema_version"] == "worker_skill.v1"
        assert 1 <= len(skill["instructions"]) <= 12
        assert forbidden.isdisjoint(skill)
        assert len(skill["content_hash"]) == 64


def test_mission_policies_define_constraints_without_fixed_execution_graphs() -> None:
    forbidden = {
        "graph_template",
        "team_policy",
        "core_templates",
        "optional_templates",
        "subagent_type",
        "runtime",
    }
    for policy in _policies():
        assert forbidden.isdisjoint(policy)
        assert policy["stage_contract_refs"]
        targets = policy["completion_contract"]["targets"]
        assert targets
        assert all(target["stage_ids"] for target in targets.values())
        assert all(target["terminal_output_kinds"] for target in targets.values())
