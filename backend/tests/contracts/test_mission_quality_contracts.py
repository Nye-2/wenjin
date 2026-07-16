import pytest
from pydantic import ValidationError

from src.contracts.research_evidence import EvidenceRecord, ResearchEvidenceBundle
from src.contracts.stage_acceptance import StageAcceptanceContract, StageCriterion
from src.contracts.versioned import contract_sha256


def test_contract_hash_is_stable_across_mapping_order() -> None:
    left = {"b": 2, "a": {"y": 2, "x": 1}}
    right = {"a": {"x": 1, "y": 2}, "b": 2}

    assert contract_sha256(left) == contract_sha256(right)


def test_stage_contract_is_frozen_and_hash_changes_with_semantics() -> None:
    contract = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="sci.scope",
        version=1,
        mission_policy_id="sci",
        workspace_type="sci",
        stage_id="scope",
        stage_goal="Bound the topic.",
        minimum_criteria=(StageCriterion(criterion_id="bounded", description="Bounded"),),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        advance_condition="Pass",
        stop_condition="Stop",
    )

    changed = contract.model_copy(update={"stage_goal": "Bound topic and data."})
    assert contract.immutable_ref().sha256 != changed.immutable_ref().sha256
    with pytest.raises(ValidationError):
        contract.stage_goal = "mutable"  # type: ignore[misc]


def test_evidence_bundle_rejects_duplicate_semantic_ids() -> None:
    evidence = EvidenceRecord(
        evidence_id="same",
        surface="literature",
        kind="source",
        status="verified",
        source_ref="doi:10.1000/test",
    )

    with pytest.raises(ValidationError, match="duplicate evidence"):
        ResearchEvidenceBundle(evidence=(evidence, evidence))
