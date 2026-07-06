from __future__ import annotations

from src.agents.harness.research_eval_surfaces import (
    required_surface_requirements_from_capability_policy,
    required_surfaces_from_capability_policy,
    validate_research_surface_enforcement,
)


def test_required_surfaces_from_capability_policy_reads_research_evidence_contract() -> None:
    surfaces = required_surfaces_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": [
                    "literature",
                    "experiment",
                    "workflow_trace",
                    "output_ref_reuse",
                    "output_ref_reuse",
                    "",
                ]
            }
        }
    )

    assert surfaces == (
        "literature",
        "experiment",
        "workflow_trace",
        "output_ref_reuse",
    )


def test_required_surfaces_from_capability_policy_uses_default_when_contract_missing() -> None:
    assert required_surfaces_from_capability_policy({}) == (
        "literature",
        "citation_strength",
        "paper_relevance",
        "experiment",
        "writing",
    )


def test_required_surfaces_from_capability_policy_rejects_unknown_surfaces() -> None:
    try:
        required_surfaces_from_capability_policy(
            {"research_evidence": {"required_surfaces": ["workflow_trace", "unknown_surface"]}}
        )
    except ValueError as exc:
        assert "unknown research evidence surfaces" in str(exc)
        assert "unknown_surface" in str(exc)
    else:
        raise AssertionError("unknown research evidence surface should fail")


def test_research_surface_registry_accepts_academic_harness_v1_surfaces() -> None:
    surfaces = required_surfaces_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": [
                    "claim_evidence_alignment",
                    "experiment_reproducibility",
                    "figure_data_consistency",
                    "review_packet_completeness",
                ]
            }
        }
    )

    assert surfaces == (
        "claim_evidence_alignment",
        "experiment_reproducibility",
        "figure_data_consistency",
        "review_packet_completeness",
    )


def test_research_surface_registry_accepts_cross_workspace_domain_surfaces() -> None:
    surfaces = required_surfaces_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": [
                    "argument_chain",
                    "protected_section_safety",
                    "prior_art_provenance",
                    "claim_support",
                    "enablement_support",
                    "drawing_consistency",
                    "feasibility_evidence",
                    "risk_evidence",
                    "milestone_realism",
                    "source_provenance",
                    "screenshot_provenance",
                    "non_fabrication_evidence",
                    "ai_use_disclosure",
                ]
            }
        }
    )

    assert surfaces == (
        "argument_chain",
        "protected_section_safety",
        "prior_art_provenance",
        "claim_support",
        "enablement_support",
        "drawing_consistency",
        "feasibility_evidence",
        "risk_evidence",
        "milestone_realism",
        "source_provenance",
        "screenshot_provenance",
        "non_fabrication_evidence",
        "ai_use_disclosure",
    )


def test_surface_enforcement_levels_are_parsed_per_surface() -> None:
    requirements = required_surface_requirements_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": ["workflow_trace", "review_packet_completeness"],
                "surface_enforcement": {
                    "workflow_trace": "required_runtime",
                    "review_packet_completeness": "required_final",
                },
            }
        }
    )

    assert [(item.surface, item.enforcement) for item in requirements] == [
        ("workflow_trace", "required_runtime"),
        ("review_packet_completeness", "required_final"),
    ]


def test_surface_enforcement_rejects_unknown_level() -> None:
    try:
        validate_research_surface_enforcement({"workflow_trace": "hard_block"})
    except ValueError as exc:
        assert "unknown research surface enforcement" in str(exc)
        assert "hard_block" in str(exc)
    else:
        raise AssertionError("unknown enforcement level should fail")
