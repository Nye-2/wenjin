"""Cross-seed invariants for lightweight mission policy architecture."""

from src.contracts.research_evidence import NON_BYPASSABLE_REVIEW_RISKS
from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


def test_policy_stage_refs_are_content_addressed_and_resolved() -> None:
    for item in MissionPolicyLoader().read_seed_items():
        policy = item["data"]
        resolved = {stage["contract_id"]: stage for stage in policy["resolved_stage_contracts"]}
        for ref in policy["stage_contract_refs"]:
            assert ref["contract_id"] in resolved
            assert len(ref["sha256"]) == 64


def test_every_review_mode_keeps_academic_risks_non_bypassable() -> None:
    for item in MissionPolicyLoader().read_seed_items():
        review = item["data"]["review_policy"]
        assert set(review["allowed_modes"]) == {
            "review_all",
            "balanced_default",
            "auto_draft",
        }
        assert set(review["non_bypassable_risks"]) >= NON_BYPASSABLE_REVIEW_RISKS


def test_worker_skills_are_bounded_resources_not_lifecycle_prompts() -> None:
    for item in SkillLoader().read_seed_items():
        skill = item["data"]
        assert skill["schema_version"] == "worker_skill.v1"
        assert 1 <= len(skill["instructions"]) <= 12
        assert sum(len(text) for text in skill["instructions"]) <= 6000
        assert "role_prompt" not in skill
        assert "quality_gates" not in skill
        assert "subagent_type" not in skill


def test_policy_route_hints_do_not_expose_internal_skill_or_schema_ids() -> None:
    for item in MissionPolicyLoader().read_seed_items():
        policy = item["data"]
        route_text = " ".join(
            [
                *policy["routing"]["when_to_use"],
                *policy["routing"]["not_for"],
                *policy["routing"]["positive_examples"],
                *policy["routing"]["negative_examples"],
            ]
        )
        assert "worker_skill.v1" not in route_text
        assert "stage_acceptance_contract.v1" not in route_text
        assert all(skill_id not in route_text for skill_id in policy["allowed_worker_skills"])


def test_policy_files_have_no_fixed_graph_or_roster_fields() -> None:
    forbidden = {
        "graph_template",
        "team_policy",
        "core_templates",
        "optional_templates",
        "quality_pipeline",
    }
    for item in MissionPolicyLoader().read_seed_items():
        policy = item["data"]
        serialized = str(policy)
        assert all(field not in serialized for field in forbidden)
