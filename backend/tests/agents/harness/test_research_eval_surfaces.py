from __future__ import annotations

from src.agents.harness.research_eval_surfaces import required_surfaces_from_capability_policy


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
