"""Pure quality-gate evaluation helpers for Team Kernel runtime."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import AgentInvocation, CapabilityTeamPolicy, QualityGateResult
from .policy import DIRECT_COMMIT_TOOLS

FOUNDATION_GATE_REQUIRED_FIELDS = {
    "query_strategy_recorded": ["query_log"],
    "source_screening_complete": [
        "included_sources",
        "borderline_sources",
        "rejected_sources",
    ],
    "claim_evidence_map_required": ["claim_evidence_map"],
    "upstream_outputs_used": ["upstream_outputs_used"],
    "unsupported_claims_marked": ["unsupported_claims"],
    "method_assumptions_logged": ["assumptions"],
    "reproducibility_status_declared": ["verified_results", "artifact_refs"],
    "review_findings_actionable": ["findings_by_severity", "required_fixes"],
    "format_requirements_checked": ["checked_requirements"],
}

FOUNDATION_GATE_ALLOW_EMPTY_FIELDS = {
    "borderline_sources",
    "rejected_sources",
    "unsupported_claims",
}

CLAIM_BINDING_GATES = {
    "claim_evidence_map_required",
    "claim_source_binding_checked",
}

CITATION_FABRICATION_GATES = {
    "no_fabricated_citations",
}


def evaluate_quality_gates(
    quality_pipeline: list[str],
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None = None,
    counts: Counter[str] | None = None,
    latest_invocations: list[AgentInvocation] | None = None,
) -> list[QualityGateResult]:
    """Evaluate runtime quality gates without mutating team state."""

    latest = latest_invocations or invocations
    total_invocations = len(invocations)
    gates: list[QualityGateResult] = []
    gates.extend(
        _foundation_field_gates(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    gates.extend(
        _pipeline_gates(
            quality_pipeline,
            invocations,
            latest=latest,
            team_policy=team_policy,
            counts=counts,
        )
    )
    gates.extend(
        _member_output_available(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    gates.extend(
        _output_schema_min_shape(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    gates.extend(
        _quality_gates_acknowledged(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    gates.extend(
        _evidence_contract_integrity(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    gates.extend(_no_direct_commit_intent(latest))
    gates.extend(
        _citation_and_evidence_required(
            latest,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
        )
    )
    return gates


def _pipeline_gates(
    quality_pipeline: list[str],
    invocations: list[AgentInvocation],
    *,
    latest: list[AgentInvocation],
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
) -> list[QualityGateResult]:
    failed = [item for item in invocations if item.status == "failed"]
    cancelled = [item for item in invocations if item.status == "cancelled"]
    interrupted = [*failed, *cancelled]
    latest_interrupted = [
        item for item in latest if item.status in {"failed", "cancelled"}
    ]
    suggested_recruits = _replacement_recruits(
        latest_interrupted,
        team_policy=team_policy,
        counts=counts,
        total_invocations=len(invocations),
    )
    status = "warning" if interrupted else "pass"
    gate_ids = [
        gate_id
        for gate_id in quality_pipeline or ["team_output_available"]
        if interrupted or gate_id not in FOUNDATION_GATE_REQUIRED_FIELDS
    ]
    if not gate_ids:
        return []
    finding_message = (
        f"{len(failed)} team member invocation(s) failed; "
        f"{len(cancelled)} cancelled"
    )
    next_action = (
        "recruit_more"
        if suggested_recruits
        else "stop_with_warning"
        if interrupted
        else "finish"
    )
    return [
        QualityGateResult(
            gate_id=gate_id,
            status=status,
            severity="medium" if interrupted else "low",
            findings=[{"message": finding_message}] if interrupted else [],
            suggested_recruits=suggested_recruits,
            next_action=next_action,
        )
        for gate_id in gate_ids
    ]


def _foundation_field_gates(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    results: list[QualityGateResult] = []
    for gate_id, required_fields in FOUNDATION_GATE_REQUIRED_FIELDS.items():
        findings: list[dict[str, Any]] = []
        suggested: list[dict[str, str]] = []
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            output = invocation.output_report if isinstance(invocation.output_report, dict) else {}
            contract = _quality_contract(invocation)
            active_gates = set(_string_list(contract.get("quality_gates")))
            if gate_id not in active_gates:
                continue
            missing = [
                field for field in required_fields
                if not _has_meaningful_field(output, field)
            ]
            if not missing:
                continue
            findings.append(
                {
                    "invocation_id": invocation.id,
                    "template_id": invocation.template_id,
                    "missing_fields": missing,
                    "message": f"required fields for {gate_id} are missing",
                }
            )
            suggested.extend(
                _revision_recruit(
                    invocation,
                    reason=gate_id,
                    team_policy=team_policy,
                    counts=counts,
                    total_invocations=total_invocations,
                    already_suggested=len(suggested),
                )
            )
        if not findings:
            continue
        missing_for_message = _dedupe(
            [
                field
                for finding in findings
                for field in _string_list(finding.get("missing_fields"))
            ]
        )
        results.append(
            QualityGateResult(
                gate_id=gate_id,
                status="fail",
                severity="medium",
                findings=findings,
                required_fixes=[
                    {
                        "message": (
                            f"Return required fields for {gate_id}: "
                            f"{', '.join(missing_for_message)}."
                        )
                    }
                ],
                suggested_recruits=_dedupe_recruits(suggested),
                next_action="revise_existing" if suggested else "stop_with_warning",
            )
        )
    return results


def _member_output_available(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    suggested: list[dict[str, str]] = []
    for invocation in invocations:
        if invocation.status != "succeeded":
            continue
        if _preview_output(invocation.output_report):
            continue
        findings.append(
            {
                "invocation_id": invocation.id,
                "template_id": invocation.template_id,
                "message": "team member succeeded without displayable output",
            }
        )
        suggested.extend(
            _revision_recruit(
                invocation,
                reason="member_output_missing",
                team_policy=team_policy,
                counts=counts,
                total_invocations=total_invocations,
                already_suggested=len(suggested),
            )
        )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="member_output_available",
            status="fail",
            severity="medium",
            findings=findings,
            required_fixes=[
                {
                    "message": "Return a non-empty summary, report_markdown, markdown, or text field."
                }
            ],
            suggested_recruits=_dedupe_recruits(suggested),
            next_action="revise_existing" if suggested else "stop_with_warning",
        )
    ]


def _output_schema_min_shape(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    suggested: list[dict[str, str]] = []
    for invocation in invocations:
        if invocation.status != "succeeded":
            continue
        contract = _quality_contract(invocation)
        output_schema = _as_dict(contract.get("output_schema"))
        if output_schema.get("type") not in {None, "object"}:
            continue
        output = invocation.output_report
        if not isinstance(output, dict):
            findings.append(
                {
                    "invocation_id": invocation.id,
                    "template_id": invocation.template_id,
                    "message": "output_report must be an object",
                }
            )
        else:
            for field in _string_list(output_schema.get("required")):
                if field not in output:
                    findings.append(
                        {
                            "invocation_id": invocation.id,
                            "template_id": invocation.template_id,
                            "field": field,
                            "message": f"required output field '{field}' is missing",
                        }
                    )
            properties = _as_dict(output_schema.get("properties"))
            for field, schema in properties.items():
                if field in output and not _matches_json_schema_type(output[field], schema):
                    findings.append(
                        {
                            "invocation_id": invocation.id,
                            "template_id": invocation.template_id,
                            "field": field,
                            "message": f"output field '{field}' has the wrong type",
                        }
                    )
        if any(item.get("invocation_id") == invocation.id for item in findings):
            suggested.extend(
                _revision_recruit(
                    invocation,
                    reason="output_schema_violation",
                    team_policy=team_policy,
                    counts=counts,
                    total_invocations=total_invocations,
                    already_suggested=len(suggested),
                )
            )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="output_schema_min_shape",
            status="fail",
            severity="medium",
            findings=findings,
            required_fixes=[
                {
                    "message": "Return all required fields with the declared JSON-compatible types."
                }
            ],
            suggested_recruits=_dedupe_recruits(suggested),
            next_action="revise_existing" if suggested else "stop_with_warning",
        )
    ]


def _quality_gates_acknowledged(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    suggested: list[dict[str, str]] = []
    for invocation in invocations:
        if invocation.status != "succeeded":
            continue
        contract = _quality_contract(invocation)
        required_gates = _string_list(contract.get("acknowledgement_required_gates"))
        if not required_gates:
            continue
        output = invocation.output_report if isinstance(invocation.output_report, dict) else {}
        checked = set(_string_list(output.get("quality_gates_checked")))
        missing = [gate for gate in required_gates if gate not in checked]
        if not missing:
            continue
        findings.append(
            {
                "invocation_id": invocation.id,
                "template_id": invocation.template_id,
                "missing_gates": missing,
                "message": "declared skill quality gates were not acknowledged",
            }
        )
        suggested.extend(
            _revision_recruit(
                invocation,
                reason="quality_gates_acknowledgement_missing",
                team_policy=team_policy,
                counts=counts,
                total_invocations=total_invocations,
                already_suggested=len(suggested),
            )
        )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="quality_gates_acknowledged",
            status="warning",
            severity="medium",
            findings=findings,
            required_fixes=[
                {
                    "message": "List checked quality gates in output.quality_gates_checked."
                }
            ],
            suggested_recruits=_dedupe_recruits(suggested),
            next_action="revise_existing" if suggested else "stop_with_warning",
        )
    ]


def _evidence_contract_integrity(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    suggested: list[dict[str, str]] = []
    for invocation in invocations:
        if invocation.status != "succeeded":
            continue
        output = invocation.output_report if isinstance(invocation.output_report, dict) else {}
        contract = _quality_contract(invocation)
        active_gates = {
            *_string_list(contract.get("quality_gates")),
            *_string_list(contract.get("acknowledgement_required_gates")),
        }
        missing_fields: list[str] = []
        if active_gates & CLAIM_BINDING_GATES and not (
            _has_meaningful_field(output, "claim_evidence_map")
            or _has_meaningful_field(output, "citation_key_audit")
        ):
            missing_fields.append("claim_evidence_map or citation_key_audit")
        if active_gates & CITATION_FABRICATION_GATES and "fabrication_risks" not in output:
            missing_fields.append("fabrication_risks")
        if not missing_fields:
            continue
        findings.append(
            {
                "invocation_id": invocation.id,
                "template_id": invocation.template_id,
                "missing_fields": missing_fields,
                "message": "evidence-dependent quality gates require structured audit fields",
            }
        )
        suggested.extend(
            _revision_recruit(
                invocation,
                reason="evidence_contract_integrity",
                team_policy=team_policy,
                counts=counts,
                total_invocations=total_invocations,
                already_suggested=len(suggested),
            )
        )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="evidence_contract_integrity",
            status="fail",
            severity="high",
            findings=findings,
            required_fixes=[
                {
                    "message": (
                        "Return structured claim/citation audit fields for "
                        "evidence-dependent quality gates."
                    )
                }
            ],
            suggested_recruits=_dedupe_recruits(suggested),
            next_action="revise_existing" if suggested else "stop_with_warning",
        )
    ]


def _no_direct_commit_intent(invocations: list[AgentInvocation]) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    for invocation in invocations:
        for tool_call in invocation.tool_calls:
            name = str(tool_call.get("name") or "")
            if name in DIRECT_COMMIT_TOOLS or name.split(".")[0] in DIRECT_COMMIT_TOOLS:
                findings.append(
                    {
                        "invocation_id": invocation.id,
                        "template_id": invocation.template_id,
                        "tool": name,
                        "message": "team member attempted direct commit tool call",
                    }
                )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="no_direct_commit_intent",
            status="fail",
            severity="high",
            findings=findings,
            required_fixes=[
                {
                    "message": "Keep team outputs staged for result_card review instead of direct room or Prism commits."
                }
            ],
            next_action="stop_with_warning",
        )
    ]


def _citation_and_evidence_required(
    invocations: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[QualityGateResult]:
    findings: list[dict[str, Any]] = []
    suggested: list[dict[str, str]] = []
    for invocation in invocations:
        if invocation.status != "succeeded" or not isinstance(invocation.output_report, dict):
            continue
        contract = _quality_contract(invocation)
        hints = _as_dict(contract.get("recruitment_hints"))
        for trigger in _open_question_triggers(invocation.output_report):
            templates = _string_list(hints.get(trigger))
            if not templates:
                continue
            findings.append(
                {
                    "invocation_id": invocation.id,
                    "template_id": invocation.template_id,
                    "trigger": trigger,
                    "message": f"output reported unresolved evidence gap '{trigger}'",
                }
            )
            suggested.extend(
                _trigger_recruits(
                    templates,
                    reason=trigger,
                    team_policy=team_policy,
                    counts=counts,
                    total_invocations=total_invocations,
                    already_suggested=len(suggested),
                )
            )
    if not findings:
        return []
    return [
        QualityGateResult(
            gate_id="citation_and_evidence_required",
            status="warning",
            severity="medium",
            findings=findings,
            required_fixes=[
                {
                    "message": "Resolve missing sources or unsupported claims before finalizing evidence-dependent output."
                }
            ],
            suggested_recruits=_dedupe_recruits(suggested),
            next_action="recruit_more" if suggested else "stop_with_warning",
        )
    ]


def _replacement_recruits(
    interrupted: list[AgentInvocation],
    *,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
) -> list[dict[str, str]]:
    if not interrupted or team_policy is None or counts is None:
        return []

    candidate_pairs: list[tuple[str, str]] = []
    if any(invocation.status == "failed" for invocation in interrupted):
        for trigger in ("member_failed", "overloaded_or_missing_specialist"):
            candidate_pairs.extend(_trigger_template_pairs(team_policy, trigger))
    if any(invocation.status == "cancelled" for invocation in interrupted):
        for trigger in ("member_cancelled", "overloaded_or_missing_specialist"):
            candidate_pairs.extend(_trigger_template_pairs(team_policy, trigger))
    if not candidate_pairs:
        candidate_pairs = [
            (template_id, "optional_fallback")
            for template_id in team_policy.optional_templates
        ]
    suggested: list[dict[str, str]] = []
    seen_templates: set[str] = set()
    for template_id, reason in candidate_pairs:
        if template_id in seen_templates:
            continue
        recruits = _trigger_recruits(
            [template_id],
            reason=reason,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations,
            already_suggested=len(suggested),
        )
        if recruits:
            suggested.extend(recruits)
            seen_templates.add(template_id)
    return _dedupe_recruits(suggested)


def _revision_recruit(
    invocation: AgentInvocation,
    *,
    reason: str,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
    already_suggested: int,
) -> list[dict[str, str]]:
    return _trigger_recruits(
        [invocation.template_id],
        reason=reason,
        team_policy=team_policy,
        counts=counts,
        total_invocations=total_invocations,
        already_suggested=already_suggested,
    )


def _trigger_recruits(
    template_ids: list[str],
    *,
    reason: str,
    team_policy: CapabilityTeamPolicy | None,
    counts: Counter[str] | None,
    total_invocations: int,
    already_suggested: int,
) -> list[dict[str, str]]:
    if team_policy is None or counts is None:
        return []
    recruits: list[dict[str, str]] = []
    for template_id in template_ids:
        if not _can_suggest_template(
            template_id,
            team_policy=team_policy,
            counts=counts,
            total_invocations=total_invocations + already_suggested + len(recruits),
        ):
            continue
        recruits.append({"template_id": template_id, "reason": reason})
    return _dedupe_recruits(recruits)


def _can_suggest_template(
    template_id: str,
    *,
    team_policy: CapabilityTeamPolicy,
    counts: Counter[str],
    total_invocations: int,
) -> bool:
    if template_id not in {*team_policy.core_templates, *team_policy.optional_templates}:
        return False
    if total_invocations >= team_policy.limits.max_invocations_total:
        return False
    return counts[template_id] < team_policy.limits.max_invocations_per_template


def _trigger_template_pairs(
    team_policy: CapabilityTeamPolicy,
    trigger_key: str,
) -> list[tuple[str, str]]:
    raw = team_policy.recruitment_triggers.get(trigger_key) or []
    return [(template_id, trigger_key) for template_id in _string_list(raw)]


def _quality_contract(invocation: AgentInvocation) -> dict[str, Any]:
    return _as_dict(invocation.input_brief.get("quality_contract"))


def _preview_output(output: Any) -> str:
    if isinstance(output, dict):
        for key in ("summary", "report_markdown", "markdown", "text"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(output or "").strip()


def _matches_json_schema_type(value: Any, schema: Any) -> bool:
    expected = _as_dict(schema).get("type")
    if expected is None:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True


def _has_meaningful_field(output: dict[str, Any], field: str) -> bool:
    if field not in output:
        return False
    value = output[field]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | dict):
        if field in FOUNDATION_GATE_ALLOW_EMPTY_FIELDS:
            return True
        return bool(value)
    return True


def _open_question_triggers(output: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    for item in output.get("open_questions") or []:
        if isinstance(item, str):
            trigger = item.strip()
        elif isinstance(item, dict):
            trigger = str(item.get("trigger") or item.get("type") or "").strip()
        else:
            trigger = ""
        if trigger:
            triggers.append(trigger)
    return _dedupe(triggers)


def _dedupe_recruits(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        template_id = str(item.get("template_id") or "")
        reason = str(item.get("reason") or "")
        key = f"{template_id}:{reason}"
        if template_id and key not in seen:
            seen.add(key)
            result.append({"template_id": template_id, "reason": reason})
    return result


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
