import pytest

from src.agents.harness.research_eval_surfaces import (
    KNOWN_RESEARCH_SURFACES,
    normalize_research_surfaces,
    validate_research_surface_enforcement,
    validate_research_surfaces,
)


def test_research_surface_vocabulary_contains_academic_trust_surfaces() -> None:
    assert {
        "claim_evidence_alignment",
        "statistical_robustness",
        "experiment_reproducibility",
        "figure_data_consistency",
        "review_packet_completeness",
    } <= KNOWN_RESEARCH_SURFACES


def test_normalize_research_surfaces_is_ordered_and_unique() -> None:
    assert normalize_research_surfaces(["literature", "claim_evidence_alignment", "literature", ""]) == ["literature", "claim_evidence_alignment"]


def test_unknown_surface_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown research evidence surfaces"):
        validate_research_surfaces(["literature", "model_said_it_is_fine"])


def test_surface_enforcement_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="unknown research surface enforcement"):
        validate_research_surface_enforcement({"literature": "best_effort"})
