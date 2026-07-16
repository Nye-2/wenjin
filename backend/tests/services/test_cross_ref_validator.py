from unittest.mock import AsyncMock

import pytest

from src.contracts.mission_policy import (
    CompletionContract,
    CompletionTarget,
    MinimumContextRequirement,
    MissionAntiExample,
    MissionExample,
    MissionGoal,
    MissionPolicy,
    MissionPolicyDisplay,
    MissionRoutingPolicy,
    ReviewPolicy,
    ToolPolicy,
    VersionedPolicyRef,
)
from src.contracts.research_evidence import NON_BYPASSABLE_REVIEW_RISKS
from src.contracts.stage_acceptance import StageAcceptanceContract, StageCriterion
from src.services.mission_policy_schema import CrossRefValidator


def _policy() -> MissionPolicy:
    stage = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="sci_research.scope_topic",
        version=1,
        mission_policy_id="sci_research",
        workspace_type="sci",
        stage_id="scope_topic",
        stage_goal="Scope",
        minimum_criteria=(StageCriterion(criterion_id="bounded", description="Bounded"),),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        advance_condition="Pass",
        stop_condition="Stop",
    )
    return MissionPolicy(
        schema_version="mission_policy.v1",
        id="sci_research",
        version=1,
        workspace_type="sci",
        display=MissionPolicyDisplay(name="SCI", description="Research"),
        routing=MissionRoutingPolicy(
            when_to_use=("research",),
            not_for=("chat",),
            positive_examples=("gap", "method", "paper"),
            negative_examples=("definition", "sentence", "list"),
        ),
        mission=MissionGoal(
            objective="Research",
            target_outcomes=("brief",),
            hard_constraints=("stage pass",),
        ),
        minimum_context={"topic": MinimumContextRequirement(requirement="required", ask="Topic?")},
        stage_contract_refs=(stage.immutable_ref(),),
        tool_policy=ToolPolicy(allowed_tool_groups=("workspace_read",)),
        allowed_worker_skills=("research-scout", "quality-critic"),
        review_policy=ReviewPolicy(non_bypassable_risks=tuple(sorted(NON_BYPASSABLE_REVIEW_RISKS))),
        sandbox_policy_ref=VersionedPolicyRef(policy_id="sandbox.research", version=1),
        examples=(
            MissionExample(
                example_id="example",
                input_summary="Grounded",
                expected_characteristics=("evidence",),
            ),
        ),
        anti_examples=(MissionAntiExample(description="Broad", failure_reason="No boundary"),),
        completion_contract=CompletionContract(
            default_target="brief",
            targets={
                "brief": CompletionTarget(
                    stage_ids=("scope_topic",),
                    terminal_output_kinds=("brief",),
                )
            },
        ),
    )


@pytest.mark.asyncio
async def test_policy_cross_ref_reports_missing_worker_skills(monkeypatch) -> None:
    validator = CrossRefValidator()
    monkeypatch.setattr(
        validator,
        "_existing_skill_ids",
        AsyncMock(return_value={"research-scout"}),
    )

    assert await validator.validate_policy(_policy()) == ["worker skill 'quality-critic' not found"]
