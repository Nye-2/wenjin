from __future__ import annotations

from datetime import UTC, datetime

from src.dataservice_client.contracts.mission import MissionItemPayload
from src.mission_runtime.reference_authority import (
    allowed_evidence_surfaces,
    evidence_authority_index,
)


def _artifact_candidate(
    *,
    reference_id: str,
    preview_text: str,
    source_refs: list[str],
) -> MissionItemPayload:
    return MissionItemPayload(
        id="item-1",
        mission_id="mission-1",
        seq=1,
        item_type="artifact",
        operation_id="create-paper",
        phase="completed",
        stage_id="paper_integration",
        producer="workspace_agent",
        summary="Integrated paper",
        payload_json={
            "reference_id": reference_id,
            "kind": "artifact_candidate",
            "title": "Integrated paper",
            "verified": True,
            "metadata": {
                "artifact_kind": "math_modeling_paper",
                "preview_text": preview_text,
                "source_refs": source_refs,
            },
        },
        payload_ref=reference_id,
        created_at=datetime.now(UTC),
    )


def test_paper_candidate_projects_content_backed_quality_surfaces() -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    source_ref = "artifact-candidate:" + "b" * 64
    visual_ref = "academic-visual:q3-policy-summary"
    item = _artifact_candidate(
        reference_id=candidate_ref,
        preview_text=(
            "# Paper\n\n"
            f"Conclusion C1 is bound to {source_ref}.\n\n"
            f"Figure 1 uses {visual_ref}.\n\n"
            "## AI 使用披露与责任\n\n"
            "D1: AI assisted with organization; the author verified all results."
        ),
        source_refs=[source_ref, visual_ref],
    )

    authority = evidence_authority_index([item])[candidate_ref]

    assert authority.surfaces == frozenset(
        {
            "writing",
            "claim_evidence_alignment",
            "ai_use_disclosure",
        }
    )
    assert authority.supported_claims == frozenset({"C1"})


def test_paper_candidate_does_not_invent_unwritten_quality_surfaces() -> None:
    candidate_ref = "artifact-candidate:" + "c" * 64
    item = _artifact_candidate(
        reference_id=candidate_ref,
        preview_text="# Paper\n\nA narrative without claim labels or disclosure.",
        source_refs=["academic-visual:q3-policy-summary"],
    )

    authority = evidence_authority_index([item])[candidate_ref]

    assert authority.surfaces == frozenset({"writing"})
    assert authority.supported_claims == frozenset()


def test_paper_candidate_does_not_claim_alignment_from_uncited_metadata() -> None:
    candidate_ref = "artifact-candidate:" + "d" * 64
    item = _artifact_candidate(
        reference_id=candidate_ref,
        preview_text="# Paper\n\nC1 is asserted without an inline source reference.",
        source_refs=["artifact-candidate:" + "e" * 64],
    )

    authority = evidence_authority_index([item])[candidate_ref]

    assert authority.surfaces == frozenset({"writing"})
    assert authority.supported_claims == frozenset()


def test_paper_candidate_requires_substantive_ai_disclosure_body() -> None:
    candidate_ref = "artifact-candidate:" + "f" * 64
    item = _artifact_candidate(
        reference_id=candidate_ref,
        preview_text="# Paper\n\n## AI 使用披露与责任\n\nshort",
        source_refs=[],
    )

    authority = evidence_authority_index([item])[candidate_ref]

    assert authority.surfaces == frozenset({"writing"})


def test_data_backed_academic_visual_projects_figure_consistency() -> None:
    metadata = {
        "candidate": {
            "source_code_hash": "a" * 64,
            "dataset_refs": ["/workspace/data.csv"],
            "source_refs": ["sandbox-file:" + "b" * 64],
            "quality_receipt": {"decoded": True, "nonblank": True},
        }
    }

    assert allowed_evidence_surfaces(
        "academic_visual_candidate", metadata
    ) == frozenset({"figure_data_consistency"})
    assert allowed_evidence_surfaces(
        "academic_visual_candidate",
        {
            "candidate": {
                **metadata["candidate"],
                "dataset_refs": [],
            }
        },
    ) == frozenset()
