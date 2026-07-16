"""Pure StageAcceptanceContract evaluator for MissionRuntime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from src.contracts.research_evidence import EvidenceRecord
from src.contracts.stage_acceptance import (
    FailureAction,
    ResolvedStageInstance,
    StageAcceptanceContract,
    StageAcceptanceResult,
    StageAssessmentInput,
    StageDecision,
    StageProgressState,
    format_stage_instance_id,
)


def evaluate_stage_acceptance(
    contract: StageAcceptanceContract,
    assessment: StageAssessmentInput,
    *,
    previous_state: StageProgressState | None = None,
    total_items: int | None = None,
) -> StageAcceptanceResult:
    """Evaluate one attempt without trusting prose or model effort labels."""

    instance = resolve_stage_instance(
        contract,
        sequence_index=assessment.sequence_index,
        total_items=total_items,
    )
    if assessment.stage_id != instance.stage_id:
        raise ValueError(f"assessment stage {assessment.stage_id!r} does not match resolved stage {instance.stage_id!r}")
    if contract.instantiation.mode == "per_item" and assessment.contract_stage_id is None:
        raise ValueError("per_item assessment requires contract_stage_id")
    if assessment.contract_stage_id not in {None, contract.stage_id}:
        raise ValueError("assessment contract_stage_id does not match stage contract")

    previous = previous_state or StageProgressState()
    criterion_results = {item.criterion_id: item for item in assessment.criterion_assessments}
    evidence_by_id: dict[str, list[EvidenceRecord]] = {}
    for item in assessment.evidence:
        evidence_by_id.setdefault(item.evidence_id, []).append(item)
    artifacts_by_id = {item.artifact_id: item for item in assessment.artifacts}
    # Only server-reconstructed evidence and artifact receipts can satisfy a
    # criterion. Model-authored references are never quality authority.
    known_refs = set(evidence_by_id) | set(artifacts_by_id)

    satisfied_criteria: list[str] = []
    missing_criteria: list[str] = []
    for criterion in contract.minimum_criteria:
        result = criterion_results.get(criterion.criterion_id)
        if result is None or result.status != "pass":
            missing_criteria.append(criterion.criterion_id)
            continue
        support_refs = set(result.supporting_refs)
        if criterion.requires_supporting_ref and not support_refs.intersection(known_refs):
            missing_criteria.append(criterion.criterion_id)
            continue
        if criterion.required_evidence_surfaces:
            supported_surfaces = {
                evidence.surface
                for ref in support_refs
                for evidence in evidence_by_id.get(ref, ())
                if evidence.status == "verified"
            }
            if not set(criterion.required_evidence_surfaces) <= supported_surfaces:
                missing_criteria.append(criterion.criterion_id)
                continue
        satisfied_criteria.append(criterion.criterion_id)

    verified_surfaces = {item.surface for item in assessment.evidence if item.status == "verified"}
    missing_evidence_surfaces = sorted(set(contract.required_evidence_surfaces) - verified_surfaces)

    missing_artifact_kinds: list[str] = []
    for requirement in contract.required_artifacts:
        matching = [artifact for artifact in assessment.artifacts if artifact.kind == requirement.kind and bool(artifact.content_hash) and (not requirement.requires_manifest or bool(artifact.manifest_ref))]
        if len(matching) < requirement.minimum_count:
            missing_artifact_kinds.append(requirement.kind)

    comparison_by_ref = {item.exemplar_ref_id: item for item in assessment.exemplar_comparisons}
    missing_exemplar_refs: list[str] = []
    if contract.require_exemplar_comparison:
        missing_exemplar_refs = sorted(ref.ref_id for ref in contract.exemplar_refs if ref.ref_id not in comparison_by_ref or comparison_by_ref[ref.ref_id].verdict not in {"meets", "exceeds"})

    has_failures = any(
        (
            missing_criteria,
            missing_evidence_surfaces,
            missing_artifact_kinds,
            missing_exemplar_refs,
        )
    )
    failure_fingerprint = (
        _failure_fingerprint(
            missing_criteria=missing_criteria,
            missing_evidence_surfaces=missing_evidence_surfaces,
            missing_artifact_kinds=missing_artifact_kinds,
            missing_exemplar_refs=missing_exemplar_refs,
            satisfied_criteria=satisfied_criteria,
            observed_evidence_refs=list(evidence_by_id),
            observed_artifact_refs=list(artifacts_by_id),
            blocking_user_inputs=list(assessment.blocking_user_inputs),
        )
        if has_failures
        else None
    )
    no_progress_count = previous.no_progress_count + 1 if failure_fingerprint and failure_fingerprint == previous.last_failure_fingerprint else 0
    attempt_count = previous.attempt_count + 1

    result: StageDecision
    next_action: FailureAction | None
    if not has_failures:
        result = "pass"
        next_action = None
    elif previous.revision_count >= contract.max_revision_attempts or no_progress_count >= contract.no_progress_limit:
        result = "stop"
        next_action = "stop_execution"
    elif assessment.blocking_user_inputs and "ask_user" in contract.allowed_actions_if_failed:
        result = "ask_user"
        next_action = "ask_user"
    else:
        result = "revise"
        next_action = _repair_action(
            contract,
            missing_evidence=bool(missing_evidence_surfaces),
        )

    revision_count = previous.revision_count + (1 if result == "revise" else 0)
    progress_state = StageProgressState(
        attempt_count=attempt_count,
        revision_count=revision_count,
        no_progress_count=no_progress_count,
        last_attempt_item_seq=assessment.item_seq or previous.last_attempt_item_seq,
        last_passed_item_seq=(assessment.item_seq if result == "pass" else previous.last_passed_item_seq),
        last_failure_fingerprint=failure_fingerprint,
        last_failed_criteria=tuple(missing_criteria),
        next_repair_action=next_action,
    )
    return StageAcceptanceResult(
        contract_ref=contract.immutable_ref(),
        stage_id=instance.stage_id,
        contract_stage_id=contract.stage_id,
        sequence_index=instance.sequence_index,
        operation_id=assessment.operation_id,
        result=result,
        satisfied_criteria=tuple(satisfied_criteria),
        missing_criteria=tuple(missing_criteria),
        missing_evidence_surfaces=tuple(missing_evidence_surfaces),
        missing_artifact_kinds=tuple(missing_artifact_kinds),
        missing_exemplar_refs=tuple(missing_exemplar_refs),
        evidence_refs=tuple(evidence_by_id),
        artifact_refs=tuple(artifacts_by_id),
        blocking_user_inputs=assessment.blocking_user_inputs,
        partial_output_refs=assessment.partial_output_refs,
        next_action=next_action,
        failure_fingerprint=failure_fingerprint,
        progress_state=progress_state,
    )


def can_start_stage(
    contract: StageAcceptanceContract,
    latest_results: Mapping[str, StageAcceptanceResult],
    *,
    sequence_index: int | None = None,
    total_items: int | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Enforce sequential stage progression, including math-modeling questions."""

    instance = resolve_stage_instance(
        contract,
        sequence_index=sequence_index,
        total_items=total_items,
    )
    missing = tuple(stage_id for stage_id in instance.prerequisite_stage_ids if stage_id not in latest_results or latest_results[stage_id].result != "pass")
    return not missing, missing


def resolve_stage_instance(
    contract: StageAcceptanceContract,
    *,
    sequence_index: int | None = None,
    total_items: int | None = None,
) -> ResolvedStageInstance:
    """Instantiate per-question gates without encoding a fixed question count."""

    rule = contract.instantiation
    prerequisites = list(contract.prerequisite_stage_ids)
    if rule.mode == "single":
        if sequence_index is not None:
            raise ValueError("single stage contract does not accept sequence_index")
        stage_id = contract.stage_id
    else:
        if sequence_index is None or sequence_index < 1:
            raise ValueError("per_item stage contract requires sequence_index >= 1")
        if total_items is not None and sequence_index > total_items:
            raise ValueError("sequence_index exceeds total_items")
        stage_id = format_stage_instance_id(rule.instance_id_template, sequence_index)
        prerequisites.extend(format_stage_instance_id(template, sequence_index) for template in rule.same_item_prerequisite_templates)
        if sequence_index > 1:
            prerequisites.extend(format_stage_instance_id(template, sequence_index - 1) for template in rule.previous_item_prerequisite_templates)

    if contract.all_item_prerequisite_templates:
        if total_items is None or total_items < 1:
            raise ValueError("all-item prerequisites require total_items >= 1")
        prerequisites.extend(format_stage_instance_id(template, index) for index in range(1, total_items + 1) for template in contract.all_item_prerequisite_templates)
    return ResolvedStageInstance(
        stage_id=stage_id,
        contract_stage_id=contract.stage_id,
        sequence_index=sequence_index,
        prerequisite_stage_ids=tuple(dict.fromkeys(prerequisites)),
    )


def required_contract_stages_passed(
    required_contract_stage_ids: tuple[str, ...],
    contracts: Sequence[StageAcceptanceContract],
    latest_results: Mapping[str, StageAcceptanceResult],
    *,
    item_counts: Mapping[str, int] | None = None,
) -> bool:
    """Check a completion target, expanding every per-item contract family."""

    item_counts = item_counts or {}
    by_stage_id = {contract.stage_id: contract for contract in contracts}
    for contract_stage_id in required_contract_stage_ids:
        contract = by_stage_id.get(contract_stage_id)
        if contract is None:
            raise ValueError(f"completion target references unknown contract stage {contract_stage_id}")
        if contract.instantiation.mode == "single":
            result = latest_results.get(contract.stage_id)
            if result is None or result.result != "pass":
                return False
            continue
        source_key = contract.instantiation.source_context_key or ""
        item_count = item_counts.get(source_key)
        if item_count is None or item_count < 1:
            return False
        for index in range(1, item_count + 1):
            instance = resolve_stage_instance(contract, sequence_index=index)
            result = latest_results.get(instance.stage_id)
            if result is None or result.result != "pass":
                return False
    return True


def _repair_action(
    contract: StageAcceptanceContract,
    *,
    missing_evidence: bool,
) -> FailureAction:
    allowed = set(contract.allowed_actions_if_failed)
    if missing_evidence and "retrieve_more_evidence" in allowed:
        return "retrieve_more_evidence"
    return "revise_existing"


def _failure_fingerprint(**values: list[str]) -> str:
    payload = {key: sorted(value) for key, value in sorted(values.items())}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
