"""Concrete, fail-closed production ports for MissionRuntime."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.agents.workspace_agent.mission_loop import WorkspaceMissionLoopAgent
from src.contracts.mission_policy import MissionPolicy
from src.contracts.research_evidence import KNOWN_RESEARCH_SURFACES, ArtifactRecord, EvidenceRecord
from src.contracts.stage_acceptance import (
    CritiqueAssessment,
    StageAcceptanceContract,
    StageAssessmentInput,
)
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import CreditReservationSettlePayload
from src.dataservice_client.contracts.mission import (
    MissionItemPayload,
    MissionReviewItemDraftPayload,
    MissionRunPayload,
)
from src.mission_runtime.adapters import (
    StageAssessmentBuilder,
    StageContractResolver,
    ToolPolicyResolver,
)
from src.mission_runtime.contracts import (
    BillingOutcome,
    MissionEventEnvelope,
    MissionPauseRequest,
    MissionStartRequest,
    ReviewCandidateBatch,
    ReviewCandidateRequest,
    StageQualityRequest,
)
from src.services.credit_service import CreditService
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    get_runtime_model_config,
)
from src.services.search import (
    MODEL_NATIVE_SEARCH_TOOL_ID,
    ModelNativeSearchInput,
    NativeSearchCapability,
    ResponsesSearchSSEParser,
    ResponsesSearchSSEProtocolError,
    model_native_search_registration,
    native_search_capability,
)
from src.tools.mission import MISSION_TOOL_GROUPS, build_mission_tool_registrations
from src.tools.orchestrator import (
    ResearchToolOutcome,
    ToolCallerKind,
    ToolCatalog,
    ToolDescriptor,
    ToolDispatchError,
    ToolErrorType,
    ToolGuardDecision,
    ToolOperation,
    ToolPolicy,
    VerificationStatus,
)
from src.workspace_events import publish_workspace_event


class MissionProductionConfigurationError(RuntimeError):
    """A required production policy, model, tool, or effect is unavailable."""


_REGISTERED_TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "model_native_web_search": (MODEL_NATIVE_SEARCH_TOOL_ID,),
    **MISSION_TOOL_GROUPS,
}
_PORT_BACKED_TOOL_GROUPS: dict[str, str] = {
    "draft_stage": "review_candidate",
}


@dataclass(frozen=True, slots=True)
class ToolGroupResolution:
    tool_ids: tuple[str, ...]
    port_capabilities: tuple[str, ...]


def require_mission_model_profile(model_id: str) -> RuntimeModelConfig:
    model = get_runtime_model_config(model_id)
    if model is None:
        raise MissionProductionConfigurationError(f"Mission model profile is unavailable: {model_id}")
    freshness = model.capability_freshness()
    profile = model.capability_profile
    if not freshness.current or not profile.protocol_conformance:
        raise MissionProductionConfigurationError(f"Mission model profile is stale or non-conformant: {model_id}")
    if not model.has_strict_tools():
        raise MissionProductionConfigurationError(f"Mission model lacks verified strict structured tools: {model_id}")
    return model


def require_native_search_capability(
    model: RuntimeModelConfig,
) -> NativeSearchCapability:
    capability = native_search_capability(model)
    if not capability.available:
        reasons = ", ".join(capability.reason_codes) or "not_verified"
        raise MissionProductionConfigurationError(f"MissionPolicy requires verified model-native web search, but the independent search transport is unavailable: {reasons}")
    return capability


class PinnedMissionStartContext:
    """Resolve DataService policy once and persist the immutable mission contract."""

    def __init__(self, dataservice: AsyncDataServiceClient) -> None:
        self._dataservice = dataservice

    async def pin(self, request: MissionStartRequest) -> MissionStartRequest:
        if not request.mission_policy_id:
            raise MissionProductionConfigurationError("MissionPolicy is required")
        model = require_mission_model_profile(request.model_id)
        if request.runtime_context_json.get("model_capability_profile_hash") != model.capability_probe_hash:
            raise MissionProductionConfigurationError("Mission model capability profile does not match the verified runtime profile")
        expected_policy_hash = str(request.runtime_context_json.get("policy_content_hash") or "")
        if len(expected_policy_hash) != 64:
            raise MissionProductionConfigurationError("MissionPolicy content hash is required from the chat routing context")

        record = await self._dataservice.get_mission_policy(
            policy_id=request.mission_policy_id,
            workspace_type=request.workspace_type,
        )
        if record is None or not record.enabled:
            raise MissionProductionConfigurationError(f"MissionPolicy is unavailable: {request.mission_policy_id}")
        raw_policy = dict(record.policy_json)
        raw_contracts = raw_policy.pop("resolved_stage_contracts", None)
        content_hash = str(raw_policy.pop("content_hash", "") or "")
        policy = record.to_contract()
        if policy.workspace_type != request.workspace_type:
            raise MissionProductionConfigurationError("MissionPolicy belongs to another workspace type")
        if not content_hash or content_hash != record.content_hash:
            raise MissionProductionConfigurationError("MissionPolicy content hash does not match its catalog record")
        if expected_policy_hash != record.content_hash:
            raise MissionProductionConfigurationError("MissionPolicy changed after the WorkspaceAgent routing context was pinned")
        if not isinstance(raw_contracts, list) or not raw_contracts:
            raise MissionProductionConfigurationError("MissionPolicy has no resolved stage contracts")
        contracts = [StageAcceptanceContract.model_validate(item) for item in raw_contracts]
        _validate_stage_contracts(policy, contracts)

        intake = request.snapshot_json.get("intake")
        target = str(intake.get("target_outcome") or "").strip() if isinstance(intake, dict) else ""
        if target not in policy.completion_contract.target_stage_sets:
            target = policy.completion_contract.default_target
        required_stage_ids = list(policy.completion_contract.target_stage_sets[target])
        contract_by_stage = {contract.stage_id: contract for contract in contracts}
        missing = [stage_id for stage_id in required_stage_ids if stage_id not in contract_by_stage]
        if missing:
            raise MissionProductionConfigurationError("Completion target references unresolved stages: " + ", ".join(missing))

        tool_groups = _resolve_tool_groups(policy)
        mission_tool_ids = set(tool_groups.tool_ids)
        skill_snapshots: dict[str, dict[str, object]] = {}
        for skill_id in policy.allowed_worker_skills:
            try:
                skill_record = await self._dataservice.get_worker_skill(skill_id)
            except Exception as exc:
                raise MissionProductionConfigurationError(
                    f"WorkerSkill is unavailable: {skill_id}"
                ) from exc
            if skill_record is None:
                raise MissionProductionConfigurationError(f"WorkerSkill is unavailable: {skill_id}")
            if not skill_record.enabled:
                raise MissionProductionConfigurationError(f"WorkerSkill is disabled: {skill_id}")
            skill = skill_record.to_contract()
            if skill.id != skill_id or skill.immutable_ref().sha256 != skill_record.content_hash:
                raise MissionProductionConfigurationError(f"WorkerSkill hash drift: {skill_id}")
            skill_tools = _resolve_tool_group_names(skill.allowed_tool_groups)
            skill_snapshots[skill_id] = {
                "content_hash": skill_record.content_hash,
                "contract": skill.model_dump(mode="json"),
                "allowed_tool_ids": [
                    tool_id for tool_id in skill_tools.tool_ids if tool_id in mission_tool_ids
                ],
            }
        search_required = "model_native_web_search" in policy.tool_policy.allowed_tool_groups
        if search_required:
            require_native_search_capability(model)
        granted_permissions = list(policy.tool_policy.allowed_tool_groups)
        if search_required:
            granted_permissions.append("external_research")
        network_profiles = ["none"]
        if search_required:
            network_profiles.append("model_provider_native_search")
        if "sandbox_compute" in policy.tool_policy.allowed_tool_groups:
            network_profiles.append("package_index_only")
        if "academic_visual_render" in policy.tool_policy.allowed_tool_groups:
            network_profiles.append("academic_visual_scoped")
        runtime_context = {
            **request.runtime_context_json,
            "policy_ref": f"{policy.id}@{record.content_hash}",
            "policy_content_hash": record.content_hash,
            "mission_policy_snapshot": policy.model_dump(mode="json"),
            "worker_skill_snapshots": skill_snapshots,
            "stage_contracts": {item.stage_id: item.model_dump(mode="json") for item in contracts},
            "completion_target": target,
            "required_stage_ids": required_stage_ids,
            "tool_policy": {
                "policy_ref": f"{policy.id}@{record.content_hash}",
                "allowed_tool_ids": list(tool_groups.tool_ids),
                "granted_permissions": granted_permissions,
                "allowed_network_profiles": network_profiles,
                "port_capabilities": list(tool_groups.port_capabilities),
            },
            "billing_estimated_credits": _estimated_credits(request),
        }
        return request.model_copy(update={"runtime_context_json": runtime_context})


class PinnedToolPolicyResolver(ToolPolicyResolver):
    async def resolve(
        self,
        mission: MissionRunPayload,
        *,
        caller_kind: ToolCallerKind,
        allowed_tools: tuple[str, ...] | None = None,
    ) -> ToolPolicy:
        _ = caller_kind
        raw = mission.runtime_context_json.get("tool_policy")
        if not isinstance(raw, dict):
            raise MissionProductionConfigurationError("Pinned Mission tool policy is unavailable")
        policy_ref = str(raw.get("policy_ref") or "")
        expected_ref = str(mission.runtime_context_json.get("policy_ref") or "")
        if not policy_ref or policy_ref != expected_ref:
            raise MissionProductionConfigurationError("Mission tool policy ref is invalid")
        permitted = tuple(str(item) for item in raw.get("allowed_tool_ids") or ())
        selected = permitted if allowed_tools is None else allowed_tools
        if not set(selected).issubset(permitted):
            raise MissionProductionConfigurationError("Subagent tool scope exceeds the pinned Mission policy")
        return ToolPolicy(
            policy_ref=policy_ref,
            allowed_tool_ids=selected,
            granted_permissions=tuple(str(item) for item in raw.get("granted_permissions") or ()),
            allowed_network_profiles=tuple(str(item) for item in raw.get("allowed_network_profiles") or ()),
        )


class PinnedStageContractResolver(StageContractResolver):
    async def resolve(
        self,
        mission: MissionRunPayload,
        stage_id: str,
    ) -> StageAcceptanceContract:
        raw = mission.runtime_context_json.get("stage_contracts")
        if not isinstance(raw, dict):
            raise MissionProductionConfigurationError(f"Pinned stage contract is unavailable: {stage_id}")
        candidate = raw.get(stage_id)
        contract = (
            StageAcceptanceContract.model_validate(candidate)
            if isinstance(candidate, dict)
            else _resolve_stage_instance_contract(raw, stage_id)
        )
        if contract is None:
            raise MissionProductionConfigurationError(f"Pinned stage contract is unavailable: {stage_id}")
        if (
            contract.mission_policy_id != mission.mission_policy_id
            or contract.workspace_type != mission.workspace_type
            or (
                contract.stage_id != stage_id
                and not _matches_instance_template(
                    contract.instantiation.instance_id_template,
                    stage_id,
                )
            )
        ):
            raise MissionProductionConfigurationError(f"Pinned stage contract is inconsistent: {stage_id}")
        return contract


def _resolve_stage_instance_contract(
    raw_contracts: dict[str, Any],
    stage_id: str,
) -> StageAcceptanceContract | None:
    for value in raw_contracts.values():
        if not isinstance(value, dict):
            continue
        contract = StageAcceptanceContract.model_validate(value)
        if contract.instantiation.mode == "per_item" and _matches_instance_template(
            contract.instantiation.instance_id_template,
            stage_id,
        ):
            return contract
    return None


def _matches_instance_template(template: str | None, stage_id: str) -> bool:
    if not template or template.count("{index}") != 1:
        return False
    prefix, suffix = template.split("{index}")
    if not stage_id.startswith(prefix) or not stage_id.endswith(suffix):
        return False
    end = len(stage_id) - len(suffix) if suffix else len(stage_id)
    index = stage_id[len(prefix) : end]
    return index.isdigit() and int(index) >= 1


class PinnedStageAssessmentBuilder(StageAssessmentBuilder):
    """Combine model judgments with receipt-backed, server-owned facts."""

    async def build(
        self,
        request: StageQualityRequest,
        contract: StageAcceptanceContract,
    ) -> StageAssessmentInput:
        raw = request.assessment_json
        if not isinstance(raw, dict):
            raise MissionProductionConfigurationError(f"Stage assessment is unavailable: {request.stage_id}")
        candidate_refs = set(request.candidate_refs)
        manifests = _candidate_manifests(request.mission, candidate_refs)
        evidence = _verified_evidence(raw.get("evidence"), request.recent_items)
        artifacts = _verified_artifacts(raw.get("artifacts"), manifests)
        critiques = _verified_critiques(
            request.recent_items,
            contract=contract,
            candidate_refs=candidate_refs,
        )
        normalized = {
            **raw,
            "stage_id": request.stage_id,
            "contract_stage_id": contract.stage_id,
            "sequence_index": _stage_instance_index(contract, request.stage_id),
            "operation_id": request.operation_id,
            "actual_model_effort": request.mission.reasoning_effort.value,
            "item_seq": request.mission.last_item_seq or None,
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "critiques": [item.model_dump(mode="json") for item in critiques],
        }
        assessment = StageAssessmentInput.model_validate(normalized)
        expected_criteria = {item.criterion_id for item in (*contract.minimum_criteria, *contract.excellent_criteria)}
        assessed = {item.criterion_id for item in assessment.criterion_assessments}
        if not assessed.issubset(expected_criteria):
            raise MissionProductionConfigurationError("Stage assessment contains criteria outside the pinned contract")
        authoritative_refs = candidate_refs | {item.evidence_id for item in evidence}
        used_refs = {ref for item in assessment.criterion_assessments for ref in item.supporting_refs}
        if not used_refs.issubset(authoritative_refs):
            raise MissionProductionConfigurationError(
                "Stage assessment cites refs without a persisted candidate or verified receipt"
            )
        return assessment


def _candidate_manifests(
    mission: MissionRunPayload,
    candidate_refs: set[str],
) -> dict[str, dict[str, Any]]:
    raw = mission.snapshot_json.get("review_candidate_manifests")
    if not isinstance(raw, dict):
        return {}
    return {
        ref: dict(value)
        for ref, value in raw.items()
        if ref in candidate_refs and isinstance(value, dict)
    }


def _stage_instance_index(
    contract: StageAcceptanceContract,
    stage_id: str,
) -> int | None:
    if contract.instantiation.mode != "per_item":
        return None
    template = contract.instantiation.instance_id_template
    if not _matches_instance_template(template, stage_id) or template is None:
        raise MissionProductionConfigurationError(
            f"Stage id does not match its pinned instance template: {stage_id}"
        )
    prefix, suffix = template.split("{index}")
    end = len(stage_id) - len(suffix) if suffix else len(stage_id)
    return int(stage_id[len(prefix) : end])


def _verified_artifacts(
    raw_artifacts: Any,
    manifests: dict[str, dict[str, Any]],
) -> tuple[ArtifactRecord, ...]:
    if not isinstance(raw_artifacts, list):
        return ()
    verified: list[ArtifactRecord] = []
    for raw in raw_artifacts:
        if not isinstance(raw, dict):
            continue
        artifact_id = str(raw.get("artifact_id") or "")
        manifest = manifests.get(artifact_id)
        if manifest is None:
            continue
        artifact_kind = str(manifest.get("artifact_kind") or "")
        preview_hash = str(manifest.get("preview_hash") or "")
        if not artifact_kind or len(preview_hash) != 64:
            continue
        if raw.get("kind") != artifact_kind or raw.get("content_hash") != preview_hash:
            continue
        verified.append(
            ArtifactRecord(
                artifact_id=artifact_id,
                kind=artifact_kind,
                content_hash=preview_hash,
                manifest_ref=f"mission-review://{artifact_id}",
                metadata={"review_status": manifest.get("status", "pending")},
            )
        )
    return tuple(verified)


def _verified_evidence(
    raw_evidence: Any,
    recent_items: list[MissionItemPayload],
) -> tuple[EvidenceRecord, ...]:
    if not isinstance(raw_evidence, list):
        return ()
    index = _receipt_evidence_index(recent_items)
    verified: list[EvidenceRecord] = []
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            continue
        evidence_id = str(raw.get("evidence_id") or "")
        surface = str(raw.get("surface") or "")
        authority = index.get(evidence_id)
        if authority is None or surface not in authority["surfaces"]:
            continue
        claim_ids = tuple(str(item) for item in raw.get("claim_ids") or ())
        supported_claims = authority["supported_claims"]
        if surface == "claim_evidence_alignment" and (
            not claim_ids or not set(claim_ids).issubset(supported_claims)
        ):
            continue
        verified.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                surface=surface,
                kind=authority["kind"],
                status="verified",
                source_ref=authority["source_ref"],
                claim_ids=claim_ids,
                metadata={"receipt_operation_id": authority["operation_id"]},
            )
        )
    return tuple(verified)


def _receipt_evidence_index(
    recent_items: list[MissionItemPayload],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in recent_items:
        raw_outcome = item.payload_json.get("research_tool_outcome")
        if not isinstance(raw_outcome, dict):
            continue
        try:
            outcome = ResearchToolOutcome.model_validate(raw_outcome)
        except ValueError:
            continue
        if outcome.verification_status not in {
            VerificationStatus.VERIFIED,
            VerificationStatus.PROVIDER_RECEIPT,
        }:
            continue
        for ref in outcome.evidence_refs:
            index[ref.ref_id] = {
                "kind": ref.kind,
                "source_ref": ref.uri,
                "operation_id": outcome.operation_id,
                "surfaces": _allowed_surfaces(ref.kind, ref.metadata),
                "supported_claims": set(),
            }
        for ref in outcome.source_refs:
            if ref.verification_status not in {
                VerificationStatus.VERIFIED,
                VerificationStatus.PROVIDER_RECEIPT,
            }:
                continue
            surfaces = {"literature", "citation_strength", "paper_relevance"}
            if ref.supported_claim_refs:
                surfaces.add("claim_evidence_alignment")
            index[ref.source_id] = {
                "kind": "source_receipt",
                "source_ref": ref.canonical_url,
                "operation_id": outcome.operation_id,
                "surfaces": surfaces,
                "supported_claims": set(ref.supported_claim_refs),
            }
    return index


def _allowed_surfaces(kind: str, metadata: dict[str, Any]) -> set[str]:
    explicit = {
        str(item)
        for item in metadata.get("surfaces") or ()
        if str(item) in KNOWN_RESEARCH_SURFACES
    }
    if explicit:
        return explicit
    if kind == "provider_search_receipt":
        return {"literature", "citation_strength", "paper_relevance"}
    if kind in {"sandbox_dataset_manifest", "sandbox_artifact_manifest"}:
        return {
            "experiment",
            "experiment_interpretation",
            "statistical_robustness",
            "experiment_reproducibility",
            "figure_data_consistency",
        }
    if kind in {"workspace_asset", "source_code", "document"}:
        return {"source_provenance", "screenshot_provenance", "workflow_trace"}
    return set()


def _verified_critiques(
    recent_items: list[MissionItemPayload],
    *,
    contract: StageAcceptanceContract,
    candidate_refs: set[str],
) -> tuple[CritiqueAssessment, ...]:
    expected_criteria = {
        item.criterion_id for item in (*contract.minimum_criteria, *contract.excellent_criteria)
    }
    by_role: dict[str, CritiqueAssessment] = {}
    for item in recent_items:
        jobs = item.payload_json.get("jobs")
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            if not isinstance(job, dict) or job.get("status") != "completed":
                continue
            result = job.get("result_json")
            if not isinstance(result, dict):
                continue
            role = str(result.get("reviewer_role") or job.get("role_label") or "")
            if role not in contract.reviewer_roles:
                continue
            reviewed_refs = {str(ref) for ref in result.get("reviewed_candidate_refs") or ()}
            if not candidate_refs or not candidate_refs.issubset(reviewed_refs):
                continue
            observed_refs = {str(ref) for ref in job.get("evidence_refs") or ()}
            required_observations = {
                f"mission-review:{candidate_ref}" for candidate_ref in candidate_refs
            }
            if not required_observations.issubset(observed_refs):
                continue
            verdict = str(result.get("verdict") or "")
            if verdict not in {"pass", "revise"}:
                continue
            criterion_ids = tuple(str(value) for value in result.get("criterion_ids") or ())
            if not criterion_ids or not set(criterion_ids).issubset(expected_criteria):
                continue
            by_role[role] = CritiqueAssessment(
                reviewer_role=role,
                verdict=verdict,
                criterion_ids=criterion_ids,
                note=str(result.get("note") or job.get("result_brief") or "")[:4000],
            )
    return tuple(by_role[role] for role in contract.reviewer_roles if role in by_role)


class StrictReviewCandidateBuilder:
    async def build_candidates(
        self,
        request: ReviewCandidateRequest,
    ) -> ReviewCandidateBatch:
        raw_items = request.candidate_json.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise MissionProductionConfigurationError("Review action requires at least one atomic preview item")
        items: list[MissionReviewItemDraftPayload] = []
        for raw_item in raw_items:
            item = MissionReviewItemDraftPayload.model_validate(raw_item)
            if not item.preview_ref and not item.preview_json:
                raise MissionProductionConfigurationError("Review candidates must include a preview")
            if item.preview_ref and item.preview_expires_at is None:
                raise MissionProductionConfigurationError(
                    "External review previews require preview_expires_at"
                )
            artifact_kind = item.preview_json.get("artifact_kind")
            if not isinstance(artifact_kind, str) or not artifact_kind.strip():
                raise MissionProductionConfigurationError(
                    "Review candidates require preview_json.artifact_kind"
                )
            if item.target_kind == "document":
                item = _compile_document_review_candidate(item)
            elif not _has_materialization_descriptor(item.preview_json):
                raise MissionProductionConfigurationError(
                    "Non-document review candidates require a canonical materialization descriptor"
                )
            items.append(item)
        summary = str(request.candidate_json.get("summary") or "").strip()
        if not summary:
            summary = f"Prepared {len(items)} reviewable change(s)"
        return ReviewCandidateBatch(items=items, summary=summary)


def _compile_document_review_candidate(
    item: MissionReviewItemDraftPayload,
) -> MissionReviewItemDraftPayload:
    if item.target_ref and (not item.base_revision_ref or not item.base_hash):
        raise MissionProductionConfigurationError(
            "Existing document candidates require base revision and hash"
        )
    preview = dict(item.preview_json)
    body = next(
        (
            value
            for key in ("body", "content", "markdown")
            if isinstance((value := preview.get(key)), str) and value.strip()
        ),
        None,
    )
    if body is None:
        raise MissionProductionConfigurationError(
            "Document review candidates require a markdown body"
        )
    payload: dict[str, Any] = {
        "content_inline": body,
        "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "mime_type": "text/markdown",
    }
    if item.target_ref is None:
        path = str(preview.get("path") or _document_path(item.title)).strip()
        payload["path"] = path
    preview["materialization"] = {
        "operation": "documents.upsert_prism_file",
        "payload": payload,
    }
    return item.model_copy(
        update={
            "target_room": "documents",
            "preview_json": preview,
        }
    )


def _document_path(title: str) -> str:
    safe_title = "".join("_" if char in {"/", "\\", "\0"} else char for char in title).strip(" .")
    return f"{safe_title or '研究产物'}.md"


def _has_materialization_descriptor(preview: dict[str, Any]) -> bool:
    descriptor = preview.get("materialization")
    if not isinstance(descriptor, dict):
        return False
    operation = descriptor.get("operation")
    payload = descriptor.get("payload")
    return isinstance(operation, str) and bool(operation.strip()) and isinstance(payload, dict)


class MissionCreditBilling:
    def __init__(self, dataservice: AsyncDataServiceClient) -> None:
        self._dataservice = dataservice
        self._credits = CreditService(dataservice=dataservice)

    async def preflight(self, request: MissionStartRequest) -> BillingOutcome:
        policy = self._credits.get_mission_billing_policy()
        if not policy.enabled:
            return BillingOutcome(allowed=True, free_policy=True)
        estimate = _estimated_credits(request)
        summary = await self._credits.get_credit_summary(request.user_id)
        if int(summary.get("spendable_credits", 0)) < estimate:
            return BillingOutcome(
                allowed=False,
                pause_request=MissionPauseRequest(
                    request_id=f"billing:{request.mission_idempotency_key}",
                    reason="budget",
                    summary="当前可用额度不足，任务尚未启动。",
                    pending_request={"required_credits": estimate},
                ),
                summary="Mission credit preflight was not approved",
            )
        return BillingOutcome(
            allowed=True,
            reservation_id=f"pending:{request.mission_idempotency_key}",
        )

    async def ensure_reservation(self, mission: MissionRunPayload) -> BillingOutcome:
        policy = self._credits.get_mission_billing_policy()
        if not policy.enabled:
            return BillingOutcome(allowed=True, free_policy=True)
        estimate = max(
            int(mission.runtime_context_json.get("billing_estimated_credits") or 0),
            1,
        )
        reservation = await self._credits.reserve_for_mission(
            user_id=mission.user_id,
            workspace_id=mission.workspace_id,
            mission_id=mission.mission_id,
            estimated_credits=estimate,
            idempotency_key=f"mission:{mission.mission_id}",
            metadata={
                "mission_policy_id": mission.mission_policy_id,
                "model_id": mission.model_id,
            },
        )
        return BillingOutcome(allowed=True, reservation_id=str(reservation.id))

    async def settle(self, mission: MissionRunPayload) -> None:
        billing = mission.snapshot_json.get("billing")
        if not isinstance(billing, dict) or billing.get("free_policy") is True:
            return
        reservation_id = str(billing.get("reservation_id") or "")
        if not reservation_id or reservation_id.startswith("pending:"):
            raise MissionProductionConfigurationError("Mission has no durable credit reservation to settle")
        estimate = max(
            int(mission.runtime_context_json.get("billing_estimated_credits") or 0),
            0,
        )
        settled_credits = estimate if mission.status.value == "completed" else 0
        await self._dataservice.settle_credit_reservation(
            reservation_id,
            CreditReservationSettlePayload(
                settled_credits=settled_credits,
                description=f"Mission {mission.title[:120]} settlement",
                mission_policy_id=mission.mission_policy_id,
                mission_id=mission.mission_id,
                metadata={
                    "mission_id": mission.mission_id,
                    "status": mission.status.value,
                },
            ),
        )


class WorkspaceMissionEventPublisher:
    async def publish(self, event: MissionEventEnvelope) -> None:
        await publish_workspace_event(
            event.workspace_id,
            event.event_type.value,
            event.model_dump(mode="json"),
        )


class CeleryMissionWakeupPublisher:
    async def publish(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
        delay_seconds: int = 0,
    ) -> None:
        from src.task.celery_app import celery_app

        kwargs: dict[str, Any] = {}
        if command_hint is not None:
            kwargs["command_hint"] = command_hint
        delivery_options: dict[str, Any] = {"queue": "long_running"}
        if delay_seconds > 0:
            delivery_options["countdown"] = delay_seconds
        celery_app.send_task(
            "src.task.tasks.drive_mission",
            args=[mission_id],
            kwargs=kwargs,
            **delivery_options,
        )


class StrictToolExecutionGuard:
    async def preflight(
        self,
        *,
        descriptor: ToolDescriptor,
        operation: ToolOperation,
        arguments: Any,
        policy: ToolPolicy,
    ) -> ToolGuardDecision:
        _ = operation, arguments
        if descriptor.tool_id not in policy.allowed_tool_ids:
            return ToolGuardDecision(
                allowed=False,
                error_type=ToolErrorType.POLICY_FORBIDDEN,
                user_safe_summary="Tool is outside the pinned Mission policy.",
            )
        return ToolGuardDecision(allowed=True)


class ResponsesSSESearchExecutor:
    """Stop at a verified response.completed event before abnormal peer close."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def __call__(
        self,
        *,
        model: RuntimeModelConfig,
        request: ModelNativeSearchInput,
    ) -> dict[str, Any]:
        endpoint = _responses_endpoint(model.base_url)
        headers = {
            **model.default_headers,
            "Authorization": f"Bearer {model.api_key}",
            "Content-Type": "application/json",
        }
        query = request.query
        if request.year_range:
            query += f"\nOnly retain sources from {request.year_range[0]} through {request.year_range[1]}."
        async with httpx.AsyncClient(
            timeout=model.timeout_seconds or 120.0,
            trust_env=False,
            transport=self._transport,
        ) as client:
            parser = ResponsesSearchSSEParser()
            try:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json={
                        "model": model.model,
                        "input": query,
                        "tools": [{"type": "web_search"}],
                        "tool_choice": "required",
                        "include": ["web_search_call.action.sources"],
                        "store": False,
                        "stream": True,
                        "reasoning": {"effort": "xhigh"},
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        completed = parser.feed_line(line)
                        if completed is not None:
                            await response.aclose()
                            return completed
                    return parser.finish()
            except ResponsesSearchSSEProtocolError as exc:
                raise ToolDispatchError(
                    ToolErrorType.PROVENANCE_MISSING,
                    "Native search did not produce a complete, cited response.",
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolDispatchError(
                    ToolErrorType.TOOL_UNAVAILABLE,
                    "Native search transport ended before a verified completion event.",
                    recoverable_by_model=True,
                ) from exc


def build_production_tool_catalog(context) -> ToolCatalog:
    registrations = [
        model_native_search_registration(executor=ResponsesSSESearchExecutor()),
        *build_mission_tool_registrations(
            dataservice=context.dataservice,
            lease_guard=context.lease_guard,
            receipt_store=context.sandbox_receipts,
        ),
    ]
    catalog = ToolCatalog(registrations).freeze()
    registered_ids = {item.tool_id for item in catalog.descriptors()}
    missing = {tool_id for tool_ids in _REGISTERED_TOOL_GROUPS.values() for tool_id in tool_ids if tool_id not in registered_ids}
    if missing:
        raise MissionProductionConfigurationError("Canonical Mission tool registrations are incomplete: " + ", ".join(sorted(missing)))
    return catalog


def production_agent() -> WorkspaceMissionLoopAgent:
    return WorkspaceMissionLoopAgent()


def _validate_stage_contracts(
    policy: MissionPolicy,
    contracts: list[StageAcceptanceContract],
) -> None:
    expected = {(item.contract_id, item.sha256) for item in policy.stage_contract_refs}
    actual = {(item.contract_id, item.immutable_ref().sha256) for item in contracts}
    if expected != actual:
        raise MissionProductionConfigurationError("Resolved StageAcceptanceContracts do not match MissionPolicy refs")


def _resolve_tool_groups(policy: MissionPolicy) -> ToolGroupResolution:
    return _resolve_tool_group_names(
        policy.tool_policy.allowed_tool_groups,
        denied_tools=policy.tool_policy.denied_tools,
    )


def _resolve_tool_group_names(
    group_names: tuple[str, ...],
    *,
    denied_tools: tuple[str, ...] = (),
) -> ToolGroupResolution:
    resolved: list[str] = []
    ports: list[str] = []
    denied = set(denied_tools)
    for group in group_names:
        if group in _REGISTERED_TOOL_GROUPS:
            registrations = tuple(tool_id for tool_id in _REGISTERED_TOOL_GROUPS[group] if tool_id not in denied)
            if not registrations:
                raise MissionProductionConfigurationError(f"MissionPolicy tool group has no permitted registration: {group}")
            resolved.extend(registrations)
            continue
        if group in _PORT_BACKED_TOOL_GROUPS:
            ports.append(_PORT_BACKED_TOOL_GROUPS[group])
            continue
        raise MissionProductionConfigurationError(f"MissionPolicy references unknown tool group or empty registration: {group}")
    return ToolGroupResolution(
        tool_ids=tuple(dict.fromkeys(resolved)),
        port_capabilities=tuple(dict.fromkeys(ports)),
    )


def _estimated_credits(request: MissionStartRequest) -> int:
    raw = request.runtime_context_json.get("billing_estimated_credits")
    if raw is None:
        raw = request.snapshot_json.get("billing_estimated_credits")
    try:
        return max(int(raw if raw is not None else 10), 1)
    except (TypeError, ValueError):
        raise MissionProductionConfigurationError("Mission billing estimate must be an integer") from None


def _responses_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    path = f"{path}/responses" if path else "/responses"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def stable_operation_id(*parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]
    return f"mission-op:{digest}"


__all__ = [
    "CeleryMissionWakeupPublisher",
    "MissionCreditBilling",
    "MissionProductionConfigurationError",
    "PinnedMissionStartContext",
    "PinnedStageAssessmentBuilder",
    "PinnedStageContractResolver",
    "PinnedToolPolicyResolver",
    "ResponsesSSESearchExecutor",
    "StrictReviewCandidateBuilder",
    "StrictToolExecutionGuard",
    "WorkspaceMissionEventPublisher",
    "build_production_tool_catalog",
    "production_agent",
    "require_mission_model_profile",
    "require_native_search_capability",
]
