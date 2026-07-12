from src.agents.harness.research_task_eval_pack import (
    ResearchTaskEvalCase,
    evaluate_research_task_eval_pack,
)
from src.contracts.research_evidence import EvidenceRecord, ResearchEvidenceBundle


def _case(case_id: str, *, verified: bool) -> ResearchTaskEvalCase:
    evidence = (
        EvidenceRecord(
            evidence_id=f"source-{case_id}",
            surface="literature",
            kind="literature",
            status="verified" if verified else "unverified",
            source_ref="doi:10.1000/test" if verified else None,
        ),
    )
    return ResearchTaskEvalCase(
        case_id=case_id,
        name=case_id,
        workspace_type="sci",
        task_kind="literature",
        required_surfaces=("literature",),
        bundle=ResearchEvidenceBundle(evidence=evidence),
    )


def test_eval_pack_aggregates_failures_by_surface() -> None:
    result = evaluate_research_task_eval_pack((_case("pass", verified=True), _case("fail", verified=False)))

    assert result.status == "fail"
    assert result.pass_count == 1
    assert result.fail_count == 1
    assert result.surface_failures == {"literature": ("fail",)}


def test_eval_pack_rejects_duplicate_case_ids() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        evaluate_research_task_eval_pack((_case("same", verified=True), _case("same", verified=True)))
