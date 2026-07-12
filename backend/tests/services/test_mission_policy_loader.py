"""MissionPolicy YAML bundle loader tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from src.contracts.mission_policy import (
    CompletionContract,
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
from src.services.mission_policy_loader import MissionPolicyLoader


class _CatalogFake:
    def __init__(self, *, has_policies: bool = False) -> None:
        self.has_mission_policies = AsyncMock(return_value=has_policies)
        self.load_mission_policy_seed_items = AsyncMock(return_value=SimpleNamespace(loaded=1))
        self.list_mission_policies = AsyncMock(return_value=[])


def _write_bundle(tmp_path):
    root = tmp_path / "capabilities"
    directory = root / "sci"
    directory.mkdir(parents=True)
    stage = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v1",
        contract_id="sci_research.scope_topic",
        version=1,
        mission_policy_id="sci_research",
        workspace_type="sci",
        stage_id="scope_topic",
        stage_goal="Freeze scope.",
        minimum_criteria=(StageCriterion(criterion_id="bounded", description="Bounded."),),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        advance_condition="Scope passes.",
        stop_condition="Scope cannot be repaired.",
    )
    policy = MissionPolicy(
        schema_version="mission_policy.v1",
        id="sci_research",
        version=1,
        workspace_type="sci",
        display=MissionPolicyDisplay(name="SCI", description="Research"),
        routing=MissionRoutingPolicy(
            when_to_use=("research",),
            not_for=("chat",),
            positive_examples=("gap", "method", "paper"),
            negative_examples=("definition", "sentence", "journal list"),
        ),
        mission=MissionGoal(
            objective="Research",
            target_outcomes=("brief",),
            hard_constraints=("stage pass",),
        ),
        minimum_context={"topic": MinimumContextRequirement(requirement="required", ask="Topic?")},
        stage_contract_refs=(stage.immutable_ref(),),
        tool_policy=ToolPolicy(allowed_tool_groups=("workspace_read",)),
        allowed_worker_skills=("task-scope-planner",),
        review_policy=ReviewPolicy(non_bypassable_risks=tuple(sorted(NON_BYPASSABLE_REVIEW_RISKS))),
        sandbox_policy_ref=VersionedPolicyRef(policy_id="sandbox.research", version=1),
        examples=(
            MissionExample(
                example_id="example-1",
                input_summary="Bounded",
                expected_characteristics=("grounded",),
            ),
        ),
        anti_examples=(MissionAntiExample(description="Broad", failure_reason="No boundary"),),
        completion_contract=CompletionContract(
            default_target="brief",
            target_stage_sets={"brief": ("scope_topic",)},
            terminal_outputs=("brief",),
        ),
    )
    (directory / "stages.yaml").write_text(yaml.safe_dump(stage.model_dump(mode="json"), sort_keys=False))
    policy_path = directory / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False))
    return root, policy_path, stage, policy


@pytest.mark.asyncio
async def test_loads_resolved_policy_bundle_when_catalog_empty(tmp_path) -> None:
    root, policy_path, stage, policy = _write_bundle(tmp_path)
    dataservice = _CatalogFake()
    loader = MissionPolicyLoader(seed_dir=root, dataservice=dataservice)

    count = await loader.load_policies_if_empty()

    assert count == 1
    command = dataservice.load_mission_policy_seed_items.await_args.args[0]
    item = command.items[0]
    assert item.data["schema_version"] == "mission_policy.v1"
    assert item.data["content_hash"] == policy.immutable_ref().sha256
    assert item.data["resolved_stage_contracts"][0]["stage_id"] == stage.stage_id
    assert item.source_path == str(policy_path)


@pytest.mark.asyncio
async def test_skips_when_policy_catalog_has_data(tmp_path) -> None:
    root, *_ = _write_bundle(tmp_path)
    dataservice = _CatalogFake(has_policies=True)
    loader = MissionPolicyLoader(seed_dir=root, dataservice=dataservice)

    assert await loader.load_policies_if_empty() == 0
    dataservice.load_mission_policy_seed_items.assert_not_awaited()


def test_stage_change_with_stale_policy_hash_fails(tmp_path) -> None:
    root, _, stage, _ = _write_bundle(tmp_path)
    changed = stage.model_copy(update={"stage_goal": "Changed without repinning."})
    (root / "sci" / "stages.yaml").write_text(yaml.safe_dump(changed.model_dump(mode="json"), sort_keys=False))

    with pytest.raises(ValueError, match="hash/version mismatch"):
        MissionPolicyLoader(seed_dir=root).read_seed_items()


def test_old_capability_schema_is_rejected(tmp_path) -> None:
    root = tmp_path / "capabilities"
    directory = root / "sci"
    directory.mkdir(parents=True)
    (directory / "old.yaml").write_text("schema_version: capability.v2\nid: old\nworkspace_type: sci\n")

    with pytest.raises(ValueError, match="unsupported schema_version"):
        MissionPolicyLoader(seed_dir=root).read_seed_items()
