"""Deterministic Mission-native research evidence tests."""

from src.agents.harness.research_task_eval import evaluate_research_task_evidence
from src.contracts.research_evidence import (
    ArtifactRecord,
    ClaimRecord,
    EvidenceRecord,
    MissionOutputEvidence,
    MissionReviewEvidence,
    ResearchEvidenceBundle,
)


def _source(evidence_id: str = "source-1") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        surface="literature",
        kind="literature",
        status="verified",
        source_ref="doi:10.1000/test",
        metadata={"relevance": "direct"},
    )


def test_verified_source_and_supported_claim_pass_core_surfaces() -> None:
    bundle = ResearchEvidenceBundle(
        evidence=(
            _source(),
            EvidenceRecord(
                evidence_id="claim-map-1",
                surface="claim_evidence_alignment",
                kind="claim_map",
                status="verified",
                source_ref="mission-item:12",
            ),
        ),
        claims=(
            ClaimRecord(
                claim_id="claim-1",
                claim_type="research_gap",
                support_status="supported",
                evidence_refs=("source-1",),
            ),
        ),
    )

    result = evaluate_research_task_evidence(
        bundle,
        required_surfaces=("literature", "paper_relevance", "claim_evidence_alignment"),
    )

    assert result.status == "pass"


def test_unsupported_claim_fails_even_when_prose_output_exists() -> None:
    bundle = ResearchEvidenceBundle(
        evidence=(_source(),),
        claims=(
            ClaimRecord(
                claim_id="claim-1",
                claim_type="contribution",
                support_status="unsupported",
            ),
        ),
        outputs=(MissionOutputEvidence(output_id="draft-1", kind="manuscript"),),
    )

    result = evaluate_research_task_evidence(
        bundle,
        required_surfaces=("claim_evidence_alignment",),
    )

    assert result.status == "fail"
    assert result.findings[0]["surface"] == "claim_evidence_alignment"


def test_reproducibility_requires_manifest_script_data_and_hash() -> None:
    incomplete = ResearchEvidenceBundle(
        artifacts=(
            ArtifactRecord(
                artifact_id="result-1",
                kind="experiment_result",
                content_hash="sha256:result",
                script_ref="artifact:solve.py",
            ),
        )
    )

    failed = evaluate_research_task_evidence(
        incomplete,
        required_surfaces=("experiment_reproducibility",),
    )
    assert failed.status == "fail"

    complete = incomplete.model_copy(
        update={
            "artifacts": (
                ArtifactRecord(
                    artifact_id="result-1",
                    kind="experiment_result",
                    content_hash="sha256:result",
                    manifest_ref="artifact:manifest.json",
                    script_ref="artifact:solve.py",
                    data_refs=("artifact:data.csv",),
                ),
            )
        }
    )
    passed = evaluate_research_task_evidence(
        complete,
        required_surfaces=("experiment_reproducibility",),
    )
    assert passed.status == "pass"


def test_high_risk_output_without_explicit_review_item_fails() -> None:
    output = MissionOutputEvidence(
        output_id="draft-1",
        kind="manuscript",
        risk_categories=("citation", "claim"),
    )
    missing_review = evaluate_research_task_evidence(
        ResearchEvidenceBundle(outputs=(output,)),
        required_surfaces=("review_packet_completeness",),
    )
    assert missing_review.status == "fail"

    bypass_attempt = evaluate_research_task_evidence(
        ResearchEvidenceBundle(
            outputs=(output,),
            review_items=(
                MissionReviewEvidence(
                    review_item_id="review-1",
                    output_ref="draft-1",
                    risk_categories=("citation", "claim"),
                    requires_user_review=False,
                ),
            ),
        ),
        required_surfaces=("review_packet_completeness",),
    )
    assert bypass_attempt.status == "fail"


def test_statistical_surface_requires_uncertainty_or_test() -> None:
    weak = EvidenceRecord(
        evidence_id="stat-1",
        surface="statistical_robustness",
        kind="statistic",
        status="verified",
        metadata={"metric": "accuracy", "sample_size": 100},
    )
    result = evaluate_research_task_evidence(
        ResearchEvidenceBundle(evidence=(weak,)),
        required_surfaces=("statistical_robustness",),
    )
    assert result.status == "fail"

    strong = weak.model_copy(update={"metadata": {**weak.metadata, "uncertainty": "95% CI"}})
    result = evaluate_research_task_evidence(
        ResearchEvidenceBundle(evidence=(strong,)),
        required_surfaces=("statistical_robustness",),
    )
    assert result.status == "pass"
