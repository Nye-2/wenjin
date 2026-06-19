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


def test_compact_research_state_merges_nested_brief_claim_and_evidence_packets() -> None:
    state = compact_research_state(
        execution_id="exec-1",
        goal="AAAI paper on federated LLM fine-tuning",
        research_brief={
            "schema_version": "wenjin.research_brief.v1",
            "brief_id": "brief-1",
            "workspace_id": "ws-1",
            "execution_id": "exec-1",
            "workspace_type": "sci",
            "capability_id": "sci_literature_positioning",
            "user_objective": "找 FedLLM 创新点",
            "research_topic": "FedLLM",
            "target_output": "文献图谱",
        },
        workspace_map_summary={"topic_hints": ["FedLLM"], "library": {"source_count": 3}},
        expert_reports=[
            {
                "claim_inventory": {
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "claim_type": "literature_position",
                            "text": "FedLLM communication remains open.",
                            "support_status": "supported",
                            "evidence_refs": ["ev-1"],
                        }
                    ]
                },
                "evidence_packet": {
                    "packet_id": "evidence-1",
                    "items": [
                        {
                            "evidence_id": "ev-1",
                            "evidence_type": "library_source",
                            "title": "FedLLM Paper",
                            "source_key": "library:paper-1",
                            "support_strength": "high",
                            "relevance": "direct",
                        }
                    ],
                    "gate_decision": {
                        "status": "warn",
                        "warnings": ["one novelty claim remains weak"],
                    },
                },
            }
        ],
        quality_state=[],
    )

    assert state.research_brief is not None
    assert state.research_brief["brief_id"] == "brief-1"
    assert state.workspace_map_summary["topic_hints"] == ["FedLLM"]
    assert state.claim_inventory[0]["claim_id"] == "claim-1"
    assert state.evidence_packet[0]["evidence_id"] == "ev-1"
    assert state.unresolved_blockers == ["one novelty claim remains weak"]
