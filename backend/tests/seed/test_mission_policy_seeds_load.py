"""Canonical MissionPolicy and StageAcceptance seed acceptance tests."""

from src.services.mission_policy_loader import MissionPolicyLoader
from src.services.skill_loader import SkillLoader


def _policies() -> list[dict]:
    return [item["data"] for item in MissionPolicyLoader().read_seed_items()]


def test_every_workspace_has_one_validated_policy() -> None:
    policies = _policies()

    assert {policy["workspace_type"] for policy in policies} == {
        "sci",
        "thesis",
        "proposal",
        "software_copyright",
        "math_modeling",
        "patent",
    }
    assert len(policies) == 6


def test_policy_catalog_contains_only_target_contract_shape() -> None:
    forbidden = {
        "graph_template",
        "team_policy",
        "methodology",
        "quality_gates",
        "research_evidence",
        "runtime",
        "ui_meta",
    }
    for policy in _policies():
        assert policy["schema_version"] == "mission_policy.v1"
        assert forbidden.isdisjoint(policy)
        assert policy["resolved_stage_contracts"]
        assert len(policy["content_hash"]) == 64


def test_all_policy_worker_skills_exist() -> None:
    skill_ids = {item["data"]["id"] for item in SkillLoader().read_seed_items()}
    for policy in _policies():
        assert set(policy["allowed_worker_skills"]) <= skill_ids


def test_all_policies_expose_only_the_new_academic_visual_seed_surface() -> None:
    skill_ids = {item["data"]["id"] for item in SkillLoader().read_seed_items()}

    assert "academic-visual-engineer" in skill_ids
    assert "figure-table-engineer" not in skill_ids
    for policy in _policies():
        assert "academic_visual_render" in policy["tool_policy"]["allowed_tool_groups"]
        assert "academic-visual-engineer" in policy["allowed_worker_skills"]
        assert "figure-table-engineer" not in policy["allowed_worker_skills"]
        assert "visual_output" in policy["review_policy"]["non_bypassable_risks"]


def test_sci_stage_contracts_cover_full_research_chain() -> None:
    policy = next(item for item in _policies() if item["workspace_type"] == "sci")
    stage_ids = {item["stage_id"] for item in policy["resolved_stage_contracts"]}

    assert stage_ids == {
        "scope_topic",
        "literature_positioning",
        "research_question",
        "method_design",
        "experiment_design",
        "writing_or_revision",
    }


def test_math_modeling_enforces_question_by_question_progression() -> None:
    policy = next(item for item in _policies() if item["workspace_type"] == "math_modeling")
    by_stage = {item["stage_id"]: item for item in policy["resolved_stage_contracts"]}

    model_rule = by_stage["question_model"]["instantiation"]
    validation_rule = by_stage["question_solution_validation"]["instantiation"]
    assert model_rule["mode"] == "per_item"
    assert model_rule["source_context_key"] == "problem_questions"
    assert model_rule["previous_item_prerequisite_templates"] == ["question_{index}_solution_validation"]
    assert validation_rule["same_item_prerequisite_templates"] == ["question_{index}_model"]
    assert by_stage["paper_integration"]["all_item_prerequisite_templates"] == ["question_{index}_solution_validation"]
