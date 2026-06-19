from src.agents.harness.research_state import ResearchStateV1, compact_research_state


def test_compact_research_state_preserves_claim_evidence_and_artifact_ids() -> None:
    state = compact_research_state(
        execution_id="exec-1",
        goal="AAAI paper on federated LLM fine-tuning",
        expert_reports=[
            {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": "FedLoRA reduces communication",
                        "support_level": "supported",
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "ev-1",
                        "source_type": "library_reference",
                        "source_id": "source-1",
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "artifact-1",
                        "kind": "report",
                        "path": "/workspace/reports/lit.md",
                    }
                ],
                "uncertainties": ["privacy evidence remains weak"],
            }
        ],
        quality_state=[{"surface": "citation_strength", "status": "warning"}],
    )

    assert isinstance(state, ResearchStateV1)
    assert state.execution_id == "exec-1"
    assert state.claims[0]["claim_id"] == "claim-1"
    assert state.evidence_index[0]["evidence_id"] == "ev-1"
    assert state.artifact_index[0]["artifact_id"] == "artifact-1"
    assert state.open_questions == ["privacy evidence remains weak"]
    assert state.quality_state[0]["surface"] == "citation_strength"
