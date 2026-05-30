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
