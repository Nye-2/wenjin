from collections import Counter

from src.agents.lead_agent.v2.team.contracts import (
    AgentInvocation,
    CapabilityTeamPolicy,
)
from src.agents.lead_agent.v2.team.quality_gates import evaluate_quality_gates


def _policy() -> CapabilityTeamPolicy:
    return CapabilityTeamPolicy(
        core_templates=["research_scout.v1"],
        optional_templates=["critical_reviewer.v1", "generalist_assistant.v1"],
        recruitment_triggers={
            "missing_sources": ["research_scout.v1"],
            "unsupported_claims": ["critical_reviewer.v1"],
            "member_failed": ["generalist_assistant.v1"],
        },
        quality_pipeline=["evidence_traceability"],
    )


def _invocation(
    *,
    template_id: str = "research_scout.v1",
    status: str = "succeeded",
    output_report: dict | None = None,
    quality_contract: dict | None = None,
    tool_calls: list[dict] | None = None,
) -> AgentInvocation:
    return AgentInvocation(
        id=f"team.1.{template_id.replace('.', '_')}.1",
        iteration=1,
        template_id=template_id,
        display_name="文献检索员",
        assigned_role="文献检索员",
        recruitment_reason="test",
        input_brief={
            "quality_contract": quality_contract
            or {
                "schema_version": "resolved_quality_contract.v1",
                "template_id": template_id,
                "output_schema": {"type": "object", "properties": {}, "required": []},
                "quality_gates": [],
                "acknowledgement_required_gates": [],
                "recruitment_hints": {},
            }
        },
        status=status,  # type: ignore[arg-type]
        output_report=output_report,
        tool_calls=tool_calls or [],
    )


def test_quality_gates_request_revision_for_schema_violation() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "research_scout.v1",
        "output_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
        "quality_gates": [],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }
    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [_invocation(output_report={"summary": "only summary"}, quality_contract=contract)],
        team_policy=_policy(),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )

    schema_gate = next(gate for gate in gates if gate.gate_id == "output_schema_min_shape")
    assert schema_gate.status == "fail"
    assert schema_gate.next_action == "revise_existing"
    assert schema_gate.required_fixes
    assert schema_gate.suggested_recruits == [
        {
            "template_id": "research_scout.v1",
            "reason": "output_schema_violation",
        }
    ]


def test_quality_gates_request_recruit_for_missing_sources() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "research_scout.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": [],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {"missing_sources": ["research_scout.v1"]},
    }
    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [
            _invocation(
                output_report={
                    "text": "source work is incomplete",
                    "open_questions": ["missing_sources"],
                },
                quality_contract=contract,
            )
        ],
        team_policy=_policy(),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )

    evidence_gate = next(
        gate for gate in gates if gate.gate_id == "citation_and_evidence_required"
    )
    assert evidence_gate.status == "warning"
    assert evidence_gate.next_action == "recruit_more"
    assert evidence_gate.suggested_recruits == [
        {
            "template_id": "research_scout.v1",
            "reason": "missing_sources",
        }
    ]


def test_quality_gates_fail_direct_commit_tool_call() -> None:
    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [
            _invocation(
                output_report={"text": "I committed the result."},
                tool_calls=[{"name": "room_commit", "status": "completed"}],
            )
        ],
        team_policy=_policy(),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )

    direct_commit_gate = next(
        gate for gate in gates if gate.gate_id == "no_direct_commit_intent"
    )
    assert direct_commit_gate.status == "fail"
    assert direct_commit_gate.severity == "high"
    assert direct_commit_gate.next_action == "stop_with_warning"
    assert direct_commit_gate.required_fixes


def test_quality_gates_preserve_failed_member_recruitment_reasons() -> None:
    policy = _policy()
    policy.recruitment_triggers["overloaded_or_missing_specialist"] = [
        "critical_reviewer.v1"
    ]
    invocation = _invocation(status="failed", output_report=None)

    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [invocation],
        team_policy=policy,
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[invocation],
    )

    pipeline_gate = next(gate for gate in gates if gate.gate_id == "evidence_traceability")
    assert pipeline_gate.next_action == "recruit_more"
    assert pipeline_gate.suggested_recruits == [
        {
            "template_id": "generalist_assistant.v1",
            "reason": "member_failed",
        },
        {
            "template_id": "critical_reviewer.v1",
            "reason": "overloaded_or_missing_specialist",
        },
    ]


def test_quality_gates_use_standby_reason_for_optional_replacement() -> None:
    invocation = _invocation(status="failed", output_report=None)

    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [invocation],
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            optional_templates=["generalist_assistant.v1"],
            recruitment_triggers={},
        ),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[invocation],
    )

    pipeline_gate = next(gate for gate in gates if gate.gate_id == "evidence_traceability")
    assert pipeline_gate.next_action == "recruit_more"
    assert pipeline_gate.suggested_recruits == [
        {
            "template_id": "generalist_assistant.v1",
            "reason": "standby_member",
        }
    ]


def test_quality_gates_request_research_revision_for_missing_query_log() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "research_scout.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["query_strategy_recorded"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {"missing_sources": ["research_scout.v1"]},
    }
    gates = evaluate_quality_gates(
        ["query_strategy_recorded"],
        [
            _invocation(
                template_id="research_scout.v1",
                output_report={"text": "searched"},
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            optional_templates=["citation_auditor.v1"],
            recruitment_triggers={"missing_sources": ["research_scout.v1"]},
        ),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "query_strategy_recorded")
    assert gate.status == "fail"
    assert gate.next_action == "revise_existing"
    assert gate.required_fixes == [
        {
            "message": "Return required fields for query_strategy_recorded: query_log."
        }
    ]
    assert gate.suggested_recruits == [
        {
            "template_id": "research_scout.v1",
            "reason": "query_strategy_recorded",
        }
    ]


def test_quality_gates_request_reviewer_revision_for_vague_findings() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "critical_reviewer.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["review_findings_actionable"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }
    gates = evaluate_quality_gates(
        ["review_findings_actionable"],
        [
            _invocation(
                template_id="critical_reviewer.v1",
                output_report={"text": "looks weak"},
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["critical_reviewer.v1"]),
        counts=Counter({"critical_reviewer.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "review_findings_actionable")
    assert gate.status == "fail"
    assert gate.next_action == "revise_existing"
    assert gate.required_fixes == [
        {
            "message": (
                "Return required fields for review_findings_actionable: "
                "findings_by_severity, required_fixes."
            )
        }
    ]


def test_quality_gates_accept_empty_marker_lists_when_present() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "research_scout.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": [
            "source_screening_complete",
            "unsupported_claims_marked",
        ],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }
    gates = evaluate_quality_gates(
        ["source_screening_complete", "unsupported_claims_marked"],
        [
            _invocation(
                template_id="research_scout.v1",
                output_report={
                    "text": "screened",
                    "included_sources": [{"source_id": "s1"}],
                    "borderline_sources": [],
                    "rejected_sources": [],
                    "unsupported_claims": [],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["research_scout.v1"]),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[],
    )

    assert not [
        gate
        for gate in gates
        if gate.gate_id in {"source_screening_complete", "unsupported_claims_marked"}
    ]


def test_quality_gates_fail_claim_evidence_map_without_source_refs() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "literature_synthesizer.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["claim_evidence_map_required"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["claim_evidence_map_required"],
        [
            _invocation(
                template_id="literature_synthesizer.v1",
                output_report={
                    "text": "claims mapped",
                    "claim_evidence_map": [
                        {
                            "claim": "Federated LLM fine-tuning reduces data sharing risk.",
                            "evidence": "Prior work discusses privacy-preserving training.",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["literature_synthesizer.v1"]),
        counts=Counter({"literature_synthesizer.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "claim_evidence_map_required")
    assert gate.status == "fail"
    assert gate.next_action == "revise_existing"
    assert gate.findings[0]["invalid_entries"] == [
        {"index": 0, "missing_fields": ["source_id_or_citation_key"]}
    ]
    assert gate.required_fixes == [
        {
            "message": (
                "Return claim_evidence_map entries with claim plus source_id "
                "or citation_key for every supported claim."
            )
        }
    ]


def test_quality_gates_accept_claim_evidence_map_with_citation_keys() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "literature_synthesizer.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["claim_evidence_map_required"],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["claim_evidence_map_required"],
        [
            _invocation(
                template_id="literature_synthesizer.v1",
                output_report={
                    "text": "claims mapped",
                    "claim_evidence_map": [
                        {
                            "claim": "Federated LLM fine-tuning reduces data sharing risk.",
                            "citation_key": "smith2026",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["literature_synthesizer.v1"]),
        counts=Counter({"literature_synthesizer.v1": 1}),
        latest_invocations=[],
    )

    assert not [gate for gate in gates if gate.gate_id == "claim_evidence_map_required"]


def test_quality_gates_fail_claim_evidence_map_with_unknown_citation_key() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "literature_synthesizer.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["claim_evidence_map_required"],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["claim_evidence_map_required"],
        [
            _invocation(
                template_id="literature_synthesizer.v1",
                output_report={
                    "text": "claims mapped",
                    "claim_evidence_map": [
                        {
                            "claim": "Federated LLM fine-tuning reduces data sharing risk.",
                            "citation_key": "missing2026",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["literature_synthesizer.v1"]),
        counts=Counter({"literature_synthesizer.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "claim_evidence_map_required")
    assert gate.status == "fail"
    assert gate.findings[0]["invalid_entries"] == [
        {"index": 0, "unknown_refs": ["missing2026"]}
    ]
    assert gate.required_fixes == [
        {
            "message": (
                "Return claim_evidence_map entries with claim plus source_id "
                "or citation_key from the current workspace Library context."
            )
        }
    ]


def test_quality_gates_fail_source_quality_audit_without_structured_fields() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "source_quality_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": [
            "source_authority_checked",
            "metadata_completeness_checked",
            "weak_support_flagged",
        ],
        "acknowledgement_required_gates": [],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["source_authority_checked", "metadata_completeness_checked", "weak_support_flagged"],
        [
            _invocation(
                template_id="source_quality_auditor.v1",
                output_report={
                    "text": "Sources look mostly good.",
                    "quality_gates_checked": [
                        "source_authority_checked",
                        "metadata_completeness_checked",
                        "weak_support_flagged",
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["source_quality_auditor.v1"]),
        counts=Counter({"source_quality_auditor.v1": 1}),
        latest_invocations=[],
    )

    gate_ids = {gate.gate_id for gate in gates}
    assert {
        "source_authority_checked",
        "metadata_completeness_checked",
        "weak_support_flagged",
    } <= gate_ids
    for gate_id in (
        "source_authority_checked",
        "metadata_completeness_checked",
        "weak_support_flagged",
    ):
        gate = next(item for item in gates if item.gate_id == gate_id)
        assert gate.status == "fail"
        assert gate.next_action == "revise_existing"
        assert gate.suggested_recruits == [
            {
                "template_id": "source_quality_auditor.v1",
                "reason": gate_id,
            }
        ]


def test_quality_gates_accept_grounded_citation_readiness_audit() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "citation_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": [
            "no_fabricated_citations",
            "claim_source_binding_checked",
            "style_consistency_checked",
        ],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["no_fabricated_citations", "claim_source_binding_checked", "style_consistency_checked"],
        [
            _invocation(
                template_id="citation_auditor.v1",
                output_report={
                    "text": "Citation audit complete.",
                    "quality_gates_checked": [
                        "no_fabricated_citations",
                        "claim_source_binding_checked",
                        "style_consistency_checked",
                    ],
                    "citation_key_audit": [
                        {
                            "citation_key": "smith2026",
                            "source_id": "source-1",
                            "status": "ready",
                            "reason": "Library source is available and metadata is complete.",
                        }
                    ],
                    "missing_sources": [],
                    "fabrication_risks": [],
                    "bibtex_projection_notes": [
                        {
                            "citation_key": "smith2026",
                            "status": "ready",
                            "reason": "Can be projected to refs.bib.",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
        latest_invocations=[],
    )

    relevant = [
        gate
        for gate in gates
        if gate.gate_id
        in {
            "no_fabricated_citations",
            "claim_source_binding_checked",
            "style_consistency_checked",
        }
    ]
    assert not [gate for gate in relevant if gate.status != "pass"]


def test_quality_gates_fail_citation_readiness_audit_with_unknown_refs() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "citation_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["claim_source_binding_checked"],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["claim_source_binding_checked"],
        [
            _invocation(
                template_id="citation_auditor.v1",
                output_report={
                    "text": "Citation audit complete.",
                    "quality_gates_checked": ["claim_source_binding_checked"],
                    "citation_key_audit": [
                        {
                            "citation_key": "missing2026",
                            "source_id": "source-unknown",
                            "status": "ready",
                            "reason": "Looks plausible.",
                        }
                    ],
                    "missing_sources": [],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "claim_source_binding_checked")
    assert gate.status == "fail"
    assert gate.findings[0]["invalid_entries"] == [
        {
            "field": "citation_key_audit",
            "index": 0,
            "unknown_refs": ["source-unknown", "missing2026"],
        }
    ]
    assert gate.required_fixes == [
        {
            "message": (
                "Return citation/source audit entries with source_id or citation_key "
                "from the current workspace Library context."
            )
        }
    ]


def test_quality_gates_fail_citation_audit_with_fabrication_risks() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "citation_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["no_fabricated_citations"],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["no_fabricated_citations"],
        [
            _invocation(
                template_id="citation_auditor.v1",
                output_report={
                    "text": "Citation audit complete.",
                    "quality_gates_checked": ["no_fabricated_citations"],
                    "fabrication_risks": [
                        {
                            "citation_key": "smith2026",
                            "source_id": "source-1",
                            "severity": "high",
                            "status": "fabricated",
                            "reason": "DOI and title do not match Library metadata.",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "no_fabricated_citations")
    assert gate.status == "fail"
    assert gate.findings[0]["invalid_entries"] == [
        {
            "field": "fabrication_risks",
            "index": 0,
            "risk_status": "fabricated",
            "severity": "high",
        }
    ]
    assert gate.findings[0]["citation_source_audit"] == [
        {
            "schema": "wenjin.quality.citation_source_audit_finding.v1",
            "invocation_id": "team.1.citation_auditor_v1.1",
            "template_id": "citation_auditor.v1",
            "display_name": "文献检索员",
            "field": "fabrication_risks",
            "index": 0,
            "risk": "fabricated",
            "severity": "high",
            "citation_key": "smith2026",
            "source_id": "source-1",
            "unknown_refs": [],
            "claim": "",
            "message": "DOI and title do not match Library metadata.",
            "suggested_action": "replace_or_remove_citation",
        }
    ]
    assert gate.required_fixes == [
        {
            "message": (
                "Resolve high-risk citation/source audit findings before finalizing "
                "evidence-dependent output."
            )
        }
    ]


def test_quality_gates_fail_citation_audit_with_not_ready_bibtex_projection() -> None:
    contract = {
        "schema_version": "resolved_quality_contract.v1",
        "template_id": "citation_auditor.v1",
        "output_schema": {"type": "object", "properties": {}, "required": []},
        "quality_gates": ["style_consistency_checked"],
        "acknowledgement_required_gates": [],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
        "recruitment_hints": {},
    }

    gates = evaluate_quality_gates(
        ["style_consistency_checked"],
        [
            _invocation(
                template_id="citation_auditor.v1",
                output_report={
                    "text": "BibTeX projection checked.",
                    "quality_gates_checked": ["style_consistency_checked"],
                    "bibtex_projection_notes": [
                        {
                            "citation_key": "smith2026",
                            "status": "not_ready",
                            "reason": "Missing venue and DOI fields for target style.",
                        }
                    ],
                },
                quality_contract=contract,
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "style_consistency_checked")
    assert gate.status == "fail"
    assert gate.findings[0]["invalid_entries"] == [
        {
            "field": "bibtex_projection_notes",
            "index": 0,
            "risk_status": "not_ready",
        }
    ]


def test_quality_gates_enforce_capability_required_research_surfaces() -> None:
    recoverable_ref = "/workspace/tmp/tasks/.harness/outputs/exec-1/runner/stdout.txt"

    gates = evaluate_quality_gates(
        [],
        [
            _invocation(
                template_id="evidence_analyst.v1",
                output_report={"summary": "ran experiment but did not inspect prior output"},
                tool_calls=[
                    {
                        "name": "sandbox.run_python",
                        "status": "completed",
                        "output_refs": [recoverable_ref],
                        "execution_lifecycle": {
                            "schema": "wenjin.sandbox.execution_lifecycle.v1",
                            "sandbox_job_id": "job-1",
                            "sandbox_environment_id": "env-1",
                            "status": "succeeded",
                            "final_status": "succeeded",
                            "exit_code": 0,
                            "outputs": {"output_refs": [recoverable_ref]},
                        },
                    }
                ],
            )
        ],
        team_policy=CapabilityTeamPolicy(
            core_templates=["evidence_analyst.v1"],
            optional_templates=[],
            quality_pipeline=[],
        ),
        capability_policy={
            "research_evidence": {
                "required_surfaces": ["workflow_trace", "output_ref_reuse"],
            }
        },
        counts=Counter({"evidence_analyst.v1": 1}),
        latest_invocations=[],
    )

    gate = next(item for item in gates if item.gate_id == "research_evidence_required")
    assert gate.status == "fail"
    assert gate.severity == "high"
    assert gate.next_action == "revise_existing"
    assert gate.required_fixes == [
        {
            "message": (
                "Satisfy capability-required research evidence surfaces before "
                "finalizing: output_ref_reuse."
            )
        }
    ]
    assert gate.findings == [
        {
            "surface": "output_ref_reuse",
            "severity": "high",
            "message": "Recoverable sandbox output refs were available but no member read them.",
        }
    ]
    assert gate.suggested_recruits == [
        {
            "template_id": "evidence_analyst.v1",
            "reason": "research_evidence_required",
        }
    ]
