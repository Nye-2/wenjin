"""Concrete, fail-closed production ports for MissionRuntime."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx

from src.agents.workspace_agent.mission_loop import WorkspaceMissionLoopAgent
from src.contracts.mission_policy import MissionPolicy
from src.contracts.research_evidence import ArtifactRecord, EvidenceRecord
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    StageAssessmentInput,
    stage_id_matches_contract,
    stage_instance_index,
)
from src.dataservice_client import AsyncDataServiceClient
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
    MissionEventEnvelope,
    MissionStartRequest,
    ReviewCandidateBatch,
    ReviewCandidateRequest,
    StageQualityRequest,
)
from src.mission_runtime.reference_authority import evidence_authority_index
from src.models.capability_profile import native_search_endpoint
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
    build_native_search_payload,
    model_native_search_registration,
    native_search_capability,
)
from src.tools.mission import MISSION_TOOL_GROUPS, build_mission_tool_registrations
from src.tools.mission.artifact_candidates import (
    artifact_candidate_content_hash,
    valid_artifact_candidate_receipt,
)
from src.tools.mission.contracts import ImportSourceCandidateInput
from src.tools.orchestrator import (
    ToolCallerKind,
    ToolCatalog,
    ToolDescriptor,
    ToolDispatchError,
    ToolErrorType,
    ToolExecutionLimit,
    ToolGuardDecision,
    ToolOperation,
    ToolPolicy,
)
from src.workspace_events import publish_workspace_event


class MissionProductionConfigurationErrorCode(StrEnum):
    """Stable reason codes for Mission start configuration failures."""

    RUNTIME_CONFIGURATION_UNAVAILABLE = "runtime_configuration_unavailable"
    NATIVE_SEARCH_UNAVAILABLE = "native_search_unavailable"


class MissionProductionConfigurationError(RuntimeError):
    """A required production policy, model, tool, or effect is unavailable."""

    def __init__(
        self,
        message: str,
        *,
        code: MissionProductionConfigurationErrorCode = (
            MissionProductionConfigurationErrorCode.RUNTIME_CONFIGURATION_UNAVAILABLE
        ),
    ) -> None:
        super().__init__(message)
        self.code = code


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
        raise MissionProductionConfigurationError(
            "MissionPolicy requires verified model-native web search, but the "
            f"independent search transport is unavailable: {reasons}",
            code=MissionProductionConfigurationErrorCode.NATIVE_SEARCH_UNAVAILABLE,
        )
    return capability


class PinnedMissionStartContext:
    """Resolve DataService policy once and persist the immutable mission contract."""

    def __init__(
        self,
        dataservice: AsyncDataServiceClient,
        *,
        tool_catalog: ToolCatalog,
    ) -> None:
        if not tool_catalog.frozen:
            raise MissionProductionConfigurationError(
                "Mission tool catalog must be frozen before start-context pinning"
            )
        self._dataservice = dataservice
        self._tool_catalog = tool_catalog

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
        try:
            policy.review_policy.require_allowed_mode(request.review_mode)
        except ValueError as exc:
            raise MissionProductionConfigurationError(str(exc)) from exc
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
        if target and target not in policy.completion_contract.targets:
            raise MissionProductionConfigurationError(
                f"Unknown completion target for MissionPolicy: {target}"
            )
        if not target:
            target = policy.completion_contract.default_target
        completion_target = policy.completion_contract.targets[target]
        required_stage_ids = list(completion_target.stage_ids)
        contract_by_stage = {contract.stage_id: contract for contract in contracts}
        missing = [stage_id for stage_id in required_stage_ids if stage_id not in contract_by_stage]
        if missing:
            raise MissionProductionConfigurationError("Completion target references unresolved stages: " + ", ".join(missing))

        tool_groups = _resolve_tool_groups(policy)
        mission_tool_ids = set(tool_groups.tool_ids)
        execution_limits = self._tool_catalog.execution_limits(
            tool_groups.tool_ids
        )
        skill_snapshots: dict[str, dict[str, object]] = {}
        for skill_id in policy.allowed_worker_skills:
            try:
                skill_record = await self._dataservice.get_worker_skill(skill_id)
            except Exception as exc:
                raise MissionProductionConfigurationError(f"WorkerSkill is unavailable: {skill_id}") from exc
            if skill_record is None:
                raise MissionProductionConfigurationError(f"WorkerSkill is unavailable: {skill_id}")
            if not skill_record.enabled:
                raise MissionProductionConfigurationError(f"WorkerSkill is disabled: {skill_id}")
            skill = skill_record.to_contract()
            if skill.id != skill_id or skill.immutable_ref().sha256 != skill_record.content_hash:
                raise MissionProductionConfigurationError(f"WorkerSkill hash drift: {skill_id}")
            skill_tools = _resolve_tool_group_names(skill.allowed_tool_groups)
            if skill_tools.port_capabilities:
                raise MissionProductionConfigurationError(
                    f"WorkerSkill cannot declare runtime port capabilities: {skill_id}"
                )
            skill_snapshots[skill_id] = {
                "content_hash": skill_record.content_hash,
                "contract": skill.model_dump(mode="json"),
                "allowed_tool_ids": [tool_id for tool_id in skill_tools.tool_ids if tool_id in mission_tool_ids],
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
            "terminal_output_kinds": list(
                completion_target.terminal_output_kinds
            ),
            "tool_policy": {
                "policy_ref": f"{policy.id}@{record.content_hash}",
                "allowed_tool_ids": list(tool_groups.tool_ids),
                "granted_permissions": granted_permissions,
                "allowed_network_profiles": network_profiles,
                "port_capabilities": list(tool_groups.port_capabilities),
                "catalog_snapshot_hash": self._tool_catalog.descriptor_snapshot_hash(),
                "execution_limits": [
                    item.model_dump(mode="json")
                    for item in execution_limits
                ],
            },
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
        catalog_snapshot_hash = str(raw.get("catalog_snapshot_hash") or "")
        if len(catalog_snapshot_hash) != 64:
            raise MissionProductionConfigurationError(
                "Pinned Mission tool catalog snapshot is unavailable"
            )
        permitted = tuple(str(item) for item in raw.get("allowed_tool_ids") or ())
        selected = permitted if allowed_tools is None else allowed_tools
        if (
            len(selected) != len(set(selected))
            or not set(selected).issubset(permitted)
        ):
            raise MissionProductionConfigurationError("Subagent tool scope exceeds the pinned Mission policy")
        raw_limits = raw.get("execution_limits")
        if not isinstance(raw_limits, list):
            raise MissionProductionConfigurationError(
                "Pinned Mission tool execution limits are unavailable"
            )
        try:
            limits = tuple(ToolExecutionLimit.model_validate(item) for item in raw_limits)
        except ValueError as exc:
            raise MissionProductionConfigurationError(
                "Pinned Mission tool execution limits are invalid"
            ) from exc
        limit_by_tool = {item.tool_id: item for item in limits}
        if (
            len(limit_by_tool) != len(limits)
            or set(limit_by_tool) != set(permitted)
        ):
            raise MissionProductionConfigurationError(
                "Pinned Mission tool execution limits do not cover the tool policy"
            )
        return ToolPolicy(
            policy_ref=policy_ref,
            allowed_tool_ids=selected,
            granted_permissions=tuple(str(item) for item in raw.get("granted_permissions") or ()),
            allowed_network_profiles=tuple(str(item) for item in raw.get("allowed_network_profiles") or ()),
            execution_limits=tuple(limit_by_tool[tool_id] for tool_id in selected),
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
        contract = StageAcceptanceContract.model_validate(candidate) if isinstance(candidate, dict) else _resolve_stage_instance_contract(raw, stage_id)
        if contract is None:
            raise MissionProductionConfigurationError(f"Pinned stage contract is unavailable: {stage_id}")
        if contract.mission_policy_id != mission.mission_policy_id or contract.workspace_type != mission.workspace_type or not stage_id_matches_contract(contract, stage_id):
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
        if contract.instantiation.mode == "per_item" and stage_id_matches_contract(contract, stage_id):
            return contract
    return None


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
        declared_evidence = _verified_evidence(
            raw.get("evidence"), request.reference_items
        )
        artifacts = _verified_candidate_artifacts(
            candidate_refs,
            request.reference_items,
            stage_id=request.stage_id,
        )
        verified_candidate_refs = {item.artifact_id for item in artifacts}
        if verified_candidate_refs != candidate_refs:
            raise MissionProductionConfigurationError(
                "Every quality candidate must be a verified artifact from the current stage"
            )
        evidence = _merge_evidence(
            _verified_candidate_evidence(candidate_refs, request.reference_items),
            declared_evidence,
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
        }
        assessment = StageAssessmentInput.model_validate(normalized)
        expected_criteria = {item.criterion_id for item in (*contract.minimum_criteria, *contract.excellent_criteria)}
        assessed = {item.criterion_id for item in assessment.criterion_assessments}
        if not assessed.issubset(expected_criteria):
            raise MissionProductionConfigurationError("Stage assessment contains criteria outside the pinned contract")
        authoritative_refs = {item.artifact_id for item in artifacts} | {
            item.evidence_id for item in evidence
        }
        used_refs = {ref for item in assessment.criterion_assessments for ref in item.supporting_refs}
        if not used_refs.issubset(authoritative_refs):
            raise MissionProductionConfigurationError("Stage assessment cites refs without a persisted candidate or verified receipt")
        return assessment


def _stage_instance_index(
    contract: StageAcceptanceContract,
    stage_id: str,
) -> int | None:
    if contract.instantiation.mode != "per_item":
        return None
    index = stage_instance_index(
        contract.instantiation.instance_id_template,
        stage_id,
    )
    if index is None:
        raise MissionProductionConfigurationError(f"Stage id does not match its pinned instance template: {stage_id}")
    return index


def _verified_candidate_artifacts(
    candidate_refs: set[str],
    reference_items: list[MissionItemPayload],
    *,
    stage_id: str,
) -> tuple[ArtifactRecord, ...]:
    if not candidate_refs:
        return ()
    verified: list[ArtifactRecord] = []
    seen: set[str] = set()
    for item in reference_items:
        if item.item_type != "artifact":
            continue
        payload = item.payload_json
        artifact_id = str(payload.get("reference_id") or "")
        if (
            artifact_id not in candidate_refs
            or artifact_id in seen
            or item.stage_id != stage_id
        ):
            continue
        if payload.get("verified") is not True:
            continue
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            continue
        tool_kind = str(payload.get("kind") or "")
        if tool_kind == "artifact_candidate":
            artifact_kind = str(metadata.get("artifact_kind") or "")
            content_hash = str(metadata.get("content_hash") or "")
            source_refs = tuple(str(ref) for ref in metadata.get("source_refs") or ())
            if (
                not artifact_kind
                or not valid_artifact_candidate_receipt(artifact_id, metadata)
            ):
                continue
            record_metadata = {
                "mime_type": metadata.get("mime_type"),
                "title": metadata.get("title"),
                "materialized": False,
            }
        elif tool_kind == "academic_visual_candidate":
            candidate = metadata.get("candidate")
            if not isinstance(candidate, dict):
                continue
            artifact_kind = _academic_visual_artifact_kind(candidate)
            content_hash = str(candidate.get("content_hash") or "")
            source_refs = tuple(str(ref) for ref in candidate.get("source_refs") or ())
            if not _valid_content_hash(content_hash):
                continue
            record_metadata = {
                "mime_type": candidate.get("mime_type"),
                "figure_type": candidate.get("figure_type"),
                "strategy": candidate.get("strategy"),
                "materialized": False,
            }
        else:
            continue
        verified.append(
            ArtifactRecord(
                artifact_id=artifact_id,
                kind=artifact_kind,
                content_hash=content_hash,
                manifest_ref=artifact_id,
                data_refs=source_refs,
                metadata=record_metadata,
            )
        )
        seen.add(artifact_id)
    return tuple(verified)


def _valid_content_hash(value: str) -> bool:
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _academic_visual_artifact_kind(candidate: dict[str, Any]) -> str:
    figure_type = str(candidate.get("figure_type") or "")
    if figure_type in {
        "data_plot",
        "experiment_plot",
        "statistical_chart",
    }:
        return "chart"
    if figure_type == "table_visual":
        return "table"
    return "figure"


def _verified_evidence(
    raw_evidence: Any,
    recent_items: list[MissionItemPayload],
) -> tuple[EvidenceRecord, ...]:
    if not isinstance(raw_evidence, list):
        return ()
    index = evidence_authority_index(recent_items)
    verified: list[EvidenceRecord] = []
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            raise MissionProductionConfigurationError(
                "Quality evidence entries must be structured objects"
            )
        evidence_id = str(raw.get("evidence_id") or "")
        surface = str(raw.get("surface") or "")
        authority = index.get(evidence_id)
        if authority is None:
            raise MissionProductionConfigurationError(
                f"Quality evidence is not backed by a verified receipt: {evidence_id}"
            )
        if surface not in authority.surfaces:
            raise MissionProductionConfigurationError(
                "Quality evidence surface is not authorized by its receipt: "
                f"{evidence_id}:{surface}"
            )
        claim_ids = tuple(str(item) for item in raw.get("claim_ids") or ())
        if surface == "claim_evidence_alignment" and (
            not claim_ids or not set(claim_ids).issubset(authority.supported_claims)
        ):
            raise MissionProductionConfigurationError(
                "Claim-evidence alignment cites claims outside the verified receipt: "
                f"{evidence_id}"
            )
        verified.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                surface=surface,
                kind=authority.kind,
                status="verified",
                source_ref=authority.source_ref,
                claim_ids=claim_ids,
                metadata={"receipt_operation_id": authority.operation_id},
            )
        )
    return tuple(verified)


def _verified_candidate_evidence(
    candidate_refs: set[str],
    reference_items: list[MissionItemPayload],
) -> tuple[EvidenceRecord, ...]:
    """Project deterministic content evidence from selected immutable candidates."""

    authorities = evidence_authority_index(reference_items)
    verified: list[EvidenceRecord] = []
    for candidate_ref in sorted(candidate_refs):
        authority = authorities.get(candidate_ref)
        if authority is None:
            continue
        for surface in sorted(authority.surfaces):
            claim_ids = (
                tuple(sorted(authority.supported_claims))
                if surface == "claim_evidence_alignment"
                else ()
            )
            verified.append(
                EvidenceRecord(
                    evidence_id=candidate_ref,
                    surface=surface,
                    kind=authority.kind,
                    status="verified",
                    source_ref=authority.source_ref,
                    claim_ids=claim_ids,
                    metadata={
                        "receipt_operation_id": authority.operation_id,
                        "authority": "content_addressed_candidate",
                    },
                )
            )
    return tuple(verified)


def _merge_evidence(
    candidate_evidence: tuple[EvidenceRecord, ...],
    declared_evidence: tuple[EvidenceRecord, ...],
) -> tuple[EvidenceRecord, ...]:
    merged: dict[tuple[str, str], EvidenceRecord] = {}
    for item in (*candidate_evidence, *declared_evidence):
        merged.setdefault((item.evidence_id, item.surface), item)
    return tuple(merged.values())


_OUTPUT_VERSION_SUFFIX = re.compile(
    r"\s*[（(](?:原版|修订版?|修改版|改进版|revised|revision|original|v\s*\d+)[^）)]*[）)]\s*$",
    re.IGNORECASE,
)


def _canonical_output_title(title: str) -> str:
    canonical = _OUTPUT_VERSION_SUFFIX.sub("", title).strip()
    return canonical or title.strip()


class StrictReviewCandidateBuilder:
    async def build_candidates(
        self,
        request: ReviewCandidateRequest,
    ) -> ReviewCandidateBatch:
        raw_items = request.candidate_json.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise MissionProductionConfigurationError("Review action requires at least one atomic preview item")
        accepted_refs = set(request.accepted_candidate_refs)
        candidates = _internal_candidate_index(request.reference_items)
        items: list[MissionReviewItemDraftPayload] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise MissionProductionConfigurationError("Review item must be an object")
            candidate_ref = str(raw_item.get("candidate_ref") or "")
            if candidate_ref not in accepted_refs:
                raise MissionProductionConfigurationError(
                    "Review action must reference a candidate accepted for this stage"
                )
            candidate = candidates.get(candidate_ref)
            if candidate is None:
                raise MissionProductionConfigurationError(
                    "Review action must reference a verified internal candidate from this Mission"
                )
            draft = {key: value for key, value in raw_item.items() if key != "candidate_ref"}
            draft.update(_review_projection(candidate_ref, candidate, draft))
            output_key = str(draft.get("output_key") or "").strip()
            request_mission = getattr(request, "mission", None)
            mission_id = str(
                getattr(request_mission, "mission_id", "")
                or getattr(candidate[0], "mission_id", "")
            )
            draft["review_item_id"] = str(
                uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        (
                            "wenjin",
                            "mission-review",
                            mission_id,
                            str(getattr(request, "stage_id", "") or ""),
                            output_key,
                            candidate_ref,
                        )
                    ),
                )
            )
            item = MissionReviewItemDraftPayload.model_validate(draft)
            item = item.model_copy(update={"title": _canonical_output_title(item.title)})
            if not item.preview_ref and not item.preview_json:
                raise MissionProductionConfigurationError("Review candidates must include a preview")
            if item.preview_ref and item.preview_expires_at is None:
                raise MissionProductionConfigurationError("External review previews require preview_expires_at")
            artifact_kind = item.preview_json.get("artifact_kind")
            if not isinstance(artifact_kind, str) or not artifact_kind.strip():
                raise MissionProductionConfigurationError("Review candidates require preview_json.artifact_kind")
            if item.target_kind == "document":
                item = _compile_document_review_candidate(item)
            elif not _has_materialization_descriptor(item.preview_json):
                raise MissionProductionConfigurationError("Non-document review candidates require a canonical materialization descriptor")
            items.append(item)
        summary = str(request.candidate_json.get("summary") or "").strip()
        if not summary:
            summary = f"Prepared {len(items)} reviewable change(s)"
        return ReviewCandidateBatch(items=items, summary=summary)


def _internal_candidate_index(
    reference_items: list[MissionItemPayload],
) -> dict[str, tuple[MissionItemPayload, dict[str, Any], str]]:
    candidates: dict[str, tuple[MissionItemPayload, dict[str, Any], str]] = {}
    for item in reference_items:
        if item.item_type != "artifact" or item.payload_json.get("verified") is not True:
            continue
        ref = str(item.payload_json.get("reference_id") or "")
        kind = str(item.payload_json.get("kind") or "")
        metadata = item.payload_json.get("metadata")
        if (
            not ref
            or kind not in {"artifact_candidate", "academic_visual_candidate"}
            or not isinstance(metadata, dict)
        ):
            continue
        if kind == "artifact_candidate" and not valid_artifact_candidate_receipt(
            ref,
            metadata,
        ):
            continue
        candidates[ref] = (item, metadata, kind)
    return candidates


def _review_projection(
    candidate_ref: str,
    candidate: tuple[MissionItemPayload, dict[str, Any], str],
    draft: dict[str, Any],
) -> dict[str, Any]:
    item, metadata, kind = candidate
    target_kind = str(draft.get("target_kind") or "")
    if kind == "artifact_candidate":
        if str(metadata.get("artifact_kind") or "") == "source_import":
            return _source_import_review_projection(
                candidate_ref,
                item=item,
                metadata=metadata,
                draft=draft,
            )
        if target_kind != "document":
            raise MissionProductionConfigurationError(
                "Text artifact candidates can only materialize as documents"
            )
        body = metadata.get("preview_text")
        if not isinstance(body, str) or not body.strip():
            raise MissionProductionConfigurationError(
                "Document candidate has no complete inline body"
            )
        expected_hash = artifact_candidate_content_hash(body)
        if str(metadata.get("content_hash") or "") != expected_hash:
            raise MissionProductionConfigurationError(
                "Document candidate content no longer matches its receipt"
            )
        return {
            "source_item_seq": item.seq,
            "preview_json": {
                "artifact_kind": str(metadata.get("artifact_kind") or "document"),
                "body": body,
                "source_refs": [str(ref) for ref in metadata.get("source_refs") or ()],
                "candidate_ref": candidate_ref,
                "content_hash": str(metadata.get("content_hash") or ""),
                "mime_type": str(metadata.get("mime_type") or "text/markdown"),
            },
        }

    if target_kind != "workspace_asset":
        raise MissionProductionConfigurationError(
            "Academic visual candidates can only materialize as workspace assets"
        )
    visual = metadata.get("candidate")
    manifest = metadata.get("manifest")
    if not isinstance(visual, dict) or not isinstance(manifest, dict):
        raise MissionProductionConfigurationError("Academic visual candidate manifest is incomplete")
    quality_receipt = visual.get("quality_receipt")
    if not isinstance(quality_receipt, dict):
        raise MissionProductionConfigurationError("Academic visual quality receipt is unavailable")
    preview_ref = str(visual.get("review_preview_ref") or "")
    expires_at = quality_receipt.get("preview_expires_at")
    if not preview_ref or expires_at is None:
        raise MissionProductionConfigurationError("Academic visual preview is unavailable")
    artifact_kind = _academic_visual_artifact_kind(visual)
    caption = str(manifest.get("caption") or "").strip() or None
    alt_text = str(manifest.get("alt_text") or "").strip() or None
    title = str(draft.get("title") or "").strip() or str(
        visual.get("figure_id") or "academic-visual"
    )
    provider_model = str(visual.get("provider_model") or "").strip() or None
    renderer_id = str(visual.get("renderer_id") or "").strip() or None
    reproducibility_status = (
        "reproducible" if visual.get("reproducibility_ref") else "not_applicable"
    )
    provenance = _academic_visual_asset_provenance(
        item=item,
        visual=visual,
        manifest=manifest,
        quality_receipt=quality_receipt,
    )
    return {
        "source_item_seq": item.seq,
        "preview_ref": preview_ref,
        "preview_expires_at": expires_at,
        "preview_json": {
            "artifact_kind": artifact_kind,
            "candidate_ref": candidate_ref,
            "figure_type": visual.get("figure_type"),
            "strategy": visual.get("strategy"),
            "evidence_level": visual.get("evidence_level"),
            "mime_type": visual.get("mime_type"),
            "source_refs": list(visual.get("source_refs") or ()),
            "dataset_refs": list(visual.get("dataset_refs") or ()),
            "reproducibility_ref": visual.get("reproducibility_ref"),
            "reproducibility_status": reproducibility_status,
            "caption": caption,
            "alt_text": alt_text,
            "renderer_id": renderer_id,
            "renderer_version": visual.get("renderer_version"),
            "provider_model": provider_model,
            "warnings": list(visual.get("warnings") or ()),
            **provenance,
            "manifest": manifest,
            "materialization": {
                "operation": "assets.create_from_preview",
                "payload": {
                    "content_hash": visual.get("preview_hash"),
                    "mime_type": visual.get("mime_type"),
                    "manifest_ref": visual.get("reproducibility_ref"),
                    "name": f"{visual.get('figure_id') or 'academic-visual'}{_visual_suffix(str(visual.get('mime_type') or ''))}",
                    "title": title,
                    "asset_kind": "academic_visual",
                    "metadata_json": {
                        "figure_id": visual.get("figure_id"),
                        "figure_type": visual.get("figure_type"),
                        "strategy": visual.get("strategy"),
                        "evidence_level": visual.get("evidence_level"),
                        "caption": caption,
                        "alt_text": alt_text,
                        "renderer_id": renderer_id,
                        "renderer_version": visual.get("renderer_version"),
                        "provider_model": provider_model,
                        "source_refs": list(visual.get("source_refs") or ()),
                        "dataset_refs": list(visual.get("dataset_refs") or ()),
                        "reproducibility_ref": visual.get("reproducibility_ref"),
                        **provenance,
                    },
                },
            },
        },
    }


def _source_import_review_projection(
    candidate_ref: str,
    *,
    item: MissionItemPayload,
    metadata: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    if draft.get("target_kind") != "source" or draft.get("target_room") != "library":
        raise MissionProductionConfigurationError(
            "Source import candidates can only materialize in the Library"
        )
    if draft.get("target_ref") is not None:
        raise MissionProductionConfigurationError(
            "Source import candidates cannot target an existing Source"
        )
    if getattr(item, "producer", None) != "tool_orchestrator":
        raise MissionProductionConfigurationError(
            "Source import candidate is not backed by the ToolOrchestrator"
        )
    payload = metadata.get("source_import_payload")
    verification_ref = str(metadata.get("verification_ref") or "")
    if not isinstance(payload, dict):
        raise MissionProductionConfigurationError(
            "Source import candidate payload is unavailable"
        )
    try:
        args = ImportSourceCandidateInput.model_validate(
            {
                "title": payload.get("title"),
                "citation_key": payload.get("citation_key"),
                "verification_ref": verification_ref,
                "source_kind": payload.get("source_kind"),
                "authors": payload.get("authors_json"),
                "year": payload.get("year"),
                "venue": payload.get("venue"),
                "doi": payload.get("doi"),
                "url": payload.get("url"),
                "abstract": payload.get("abstract"),
            }
        )
    except ValueError as exc:
        raise MissionProductionConfigurationError(
            "Source import candidate metadata is invalid"
        ) from exc
    expected_payload = {
        "source_kind": args.source_kind,
        "title": args.title,
        "authors_json": list(args.authors),
        "year": args.year,
        "venue": args.venue,
        "doi": args.doi,
        "url": args.url,
        "abstract": args.abstract,
        "ingest_kind": "mission_verified",
        "ingest_label": verification_ref,
        "library_status": "candidate",
        "evidence_level": (
            "uploaded_fulltext"
            if verification_ref.startswith("asset:")
            else "external_verified"
        ),
        "citation_key": args.citation_key,
    }
    receipt_operation_key = str(
        item.payload_json.get("receipt_operation_key") or ""
    )
    item_operation_id = str(getattr(item, "operation_id", None) or "")
    candidate_operation_key = str(metadata.get("operation_key") or "")
    candidate_mission_id = str(metadata.get("mission_id") or "")
    item_mission_id = str(getattr(item, "mission_id", None) or "")
    if (
        payload != expected_payload
        or metadata.get("source_refs") != [verification_ref]
        or str(metadata.get("title") or "") != args.title
        or not _valid_source_verification_ref(verification_ref)
        or not candidate_operation_key
        or candidate_operation_key
        not in {receipt_operation_key, item_operation_id}
        or not candidate_mission_id
        or candidate_mission_id != item_mission_id
    ):
        raise MissionProductionConfigurationError(
            "Source import candidate receipt metadata is inconsistent"
        )
    uri = str(item.payload_json.get("uri") or "") or None
    if args.url != uri or (args.url is not None and not _valid_source_url(args.url)):
        raise MissionProductionConfigurationError(
            "Source import candidate URL does not match its verified receipt"
        )
    return {
        "source_item_seq": item.seq,
        "preview_json": {
            "artifact_kind": "source_import",
            "candidate_ref": candidate_ref,
            "verification_ref": verification_ref,
            "citation_key": args.citation_key,
            "title": args.title,
            "authors": list(args.authors),
            "year": args.year,
            "venue": args.venue,
            "doi": args.doi,
            "url": args.url,
            "abstract": args.abstract,
            "source_refs": [verification_ref],
            "content_hash": str(metadata.get("content_hash") or ""),
            "materialization": {
                "operation": "library.import_source",
                "payload": expected_payload,
            },
        },
    }


def _valid_source_verification_ref(value: str) -> bool:
    if re.fullmatch(r"(?:asset|source):[A-Za-z0-9][A-Za-z0-9._:-]{0,999}", value):
        return True
    return (
        re.fullmatch(
            r"search-receipt:[A-Za-z0-9][A-Za-z0-9._:-]{0,499}#[A-Za-z0-9][A-Za-z0-9._:-]{0,499}",
            value,
        )
        is not None
    )


def _valid_source_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and port in {None, 80, 443}
    )


def _academic_visual_asset_provenance(
    *,
    item: MissionItemPayload,
    visual: dict[str, Any],
    manifest: dict[str, Any],
    quality_receipt: dict[str, Any],
) -> dict[str, Any]:
    source_prompt_hash = visual.get("source_prompt_hash") or manifest.get(
        "source_prompt_hash"
    )
    source_code_hash = visual.get("source_code_hash") or manifest.get(
        "source_code_hash"
    )
    context_hash = visual.get("context_hash") or manifest.get("context_hash")
    prompt_contract_version = visual.get(
        "prompt_contract_version"
    ) or manifest.get("prompt_contract_version")
    overlay_hash = visual.get("overlay_manifest_hash") or manifest.get(
        "overlay_manifest_hash"
    )
    return {
        "generated_by": "wenjin_academic_visual",
        "mission_id": item.mission_id,
        "source_item_seq": item.seq,
        "content_hash": visual.get("preview_hash") or visual.get("content_hash"),
        "candidate_content_hash": visual.get("content_hash"),
        "source_prompt_hash": source_prompt_hash,
        "prompt_hash": source_prompt_hash,
        "prompt_contract_version": prompt_contract_version,
        "source_code_hash": source_code_hash,
        "source_code_ref": manifest.get("source_code_ref"),
        "context_hash": context_hash,
        "dimensions": {
            "width": visual.get("width"),
            "height": visual.get("height"),
        },
        "quality": dict(quality_receipt),
        "quality_receipt": dict(quality_receipt),
        "ai_generated": bool(
            visual.get("ai_generated", manifest.get("ai_generated", False))
        ),
        "overlay_manifest_hash": overlay_hash,
        "dataset_content_hashes": dict(
            visual.get("dataset_content_hashes")
            or manifest.get("dataset_content_hashes")
            or {}
        ),
        "source_content_hashes": dict(
            visual.get("source_content_hashes")
            or manifest.get("source_content_hashes")
            or {}
        ),
    }


def _visual_suffix(mime_type: str) -> str:
    return {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get(mime_type, "")


def _compile_document_review_candidate(
    item: MissionReviewItemDraftPayload,
) -> MissionReviewItemDraftPayload:
    if item.target_ref and (not item.base_revision_ref or not item.base_hash):
        raise MissionProductionConfigurationError("Existing document candidates require base revision and hash")
    if item.target_ref and not item.target_ref.startswith("prism-file:"):
        raise MissionProductionConfigurationError("Existing document candidates require a canonical Prism file ref")
    if item.target_ref and item.base_revision_ref == item.target_ref:
        raise MissionProductionConfigurationError("Existing document base revision must come from tool metadata")
    preview = dict(item.preview_json)
    if "sources" in preview:
        raise MissionProductionConfigurationError(
            "Document review candidates use preview_json.source_refs; preview_json.sources is not valid"
        )
    source_refs = preview.get("source_refs")
    if source_refs is not None and (
        not isinstance(source_refs, list)
        or not all(isinstance(ref, str) and ":" in ref for ref in source_refs)
    ):
        raise MissionProductionConfigurationError(
            "Document review candidate source_refs must be canonical reference strings"
        )
    body = next(
        (value for key in ("body", "content", "markdown") if isinstance((value := preview.get(key)), str) and value.strip()),
        None,
    )
    if body is None:
        raise MissionProductionConfigurationError("Document review candidates require a markdown body")
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
        endpoint = native_search_endpoint(model.base_url)
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
                    json=build_native_search_payload(
                        model_name=model.model,
                        query=query,
                    ),
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


def stable_operation_id(*parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]
    return f"mission-op:{digest}"


__all__ = [
    "CeleryMissionWakeupPublisher",
    "MissionProductionConfigurationError",
    "MissionProductionConfigurationErrorCode",
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
