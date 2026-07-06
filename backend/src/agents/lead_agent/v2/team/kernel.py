"""Team-kernel runtime for capability-driven dynamic Lead Agent teams."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import (
    DocumentData,
    DocumentOutput,
    ResultError,
    ResultOutput,
    ReviewPacket,
    TaskReport,
)
from src.agents.harness.diff_tracker import (
    build_harness_node_metadata_from_tool_calls,
    build_harness_replan_signals_from_tool_calls,
)
from src.agents.harness.research_brief import build_research_brief
from src.agents.harness.research_eval_surfaces import required_surfaces_from_capability_policy
from src.agents.harness.research_state import ResearchStateV1, compact_research_state
from src.agents.harness.research_task_eval import evaluate_research_task_evidence
from src.agents.lead_agent.v2.capability_preflight import (
    CapabilityPreflightError,
    validate_research_evidence_policy,
)
from src.agents.lead_agent.v2.output_mapping import (
    OutputMappingResolver,
    review_packet_from_expert_reports,
)
from src.agents.lead_agent.v2.prism_review_staging import (
    build_prism_file_change_command,
)
from src.agents.lead_agent.v2.sandbox_artifact_review import (
    collect_sandbox_artifact_candidates,
    sandbox_artifact_payload_for_candidate,
    sandbox_review_item_projection,
    workspace_asset_payload_for_candidate,
)
from src.config.llm_config import LLMSettings
from src.contracts.workspace_academic_map import compact_workspace_map_summary
from src.dataservice_client.contracts.execution import ExecutionUpdatePayload
from src.dataservice_client.provider import dataservice_client
from src.services.prism_review_projection import prism_review_item_projection
from src.services.workspace_academic_map_service import build_academic_workspace_map_from_workspace_data
from src.subagents.v2 import types as _types  # noqa: F401
from src.subagents.v2.base import SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY

from .contracts import (
    AgentInvocation,
    AgentTemplate,
    CapabilityTeamPolicy,
    QualityGateResult,
    TeamBlackboard,
)
from .episode import (
    bounded_harness_episode,
    finish_harness_episode,
    record_replan_decision,
    start_harness_episode,
    stop_reason_from_gates,
)
from .expert_runtime import (
    build_expert_node_metadata,
    build_expert_output_preview_item,
    expert_report_from_member_output,
    merge_expert_preview_items,
    merge_expert_snapshot_items,
    sanitize_expert_preview_items,
    sanitize_expert_snapshot_items,
)
from .member_context import build_team_member_context
from .policy import (
    TeamPolicyError,
    build_capability_team_policy,
    build_invocation_assignment,
    resolve_effective_skills,
    resolve_effective_tools,
)
from .quality_contract import QualityContractResolver
from .quality_gates import evaluate_quality_gates

logger = logging.getLogger(__name__)

DEFAULT_INVOCATION_TIMEOUT_SECONDS = 120.0
BLACKBOARD_ACCUMULATING_FIELDS = (
    "confirmed_findings",
    "evidence_items",
    "citation_gaps",
    "experiment_gaps",
    "data_gaps",
    "figure_table_requirements",
    "writing_risks",
    "format_risks",
    "pending_decisions",
    "rejected_claims",
)
FINAL_REPORT_RESEARCH_EVIDENCE_SURFACES = {
    "claim_evidence_alignment",
    "review_packet_completeness",
}


@dataclass(frozen=True, slots=True)
class RecruitmentCandidate:
    template_id: str
    reason: str


@dataclass(slots=True)
class SkillCatalogCache:
    records: dict[str, Any | None] = field(default_factory=dict)
    loaded: bool = False


def build_academic_harness_outputs(
    *,
    execution_id: str,
    capability_id: str,
    capability_name: str,
    expert_reports: list[Any],
    completion_status: str,
    quality_state: list[dict[str, Any]],
    research_brief: dict[str, Any] | None = None,
    workspace_map_summary: dict[str, Any] | None = None,
) -> tuple[ReviewPacket, ResearchStateV1]:
    """Build Review Packet and compact research state from expert outputs."""

    packet = review_packet_from_expert_reports(
        execution_id=execution_id,
        capability_id=capability_id,
        title=capability_name,
        reports=expert_reports,
        completion_status=completion_status,
    )
    research_state = compact_research_state(
        execution_id=execution_id,
        goal=capability_name,
        expert_reports=[report.model_dump(mode="json") for report in expert_reports],
        quality_state=quality_state,
        research_brief=research_brief,
        workspace_map_summary=workspace_map_summary,
    )
    return packet, research_state


class TeamKernelRuntime:
    """Fixed control loop for dynamic Lead Agent team execution."""

    def __init__(
        self,
        *,
        publish_event: Callable[[str, str, dict[str, Any]], Awaitable[None]],
        record_node_event: Callable[..., Awaitable[None]],
        abort_check: Callable[[str], Awaitable[bool]],
        load_workspace_data: Callable[..., Awaitable[dict[str, Any]]],
        needs_workspace_context: Callable[[dict[str, Any], dict[str, bool]], bool],
        context_requirements_from_brief: Callable[[TaskBrief], dict[str, bool]],
        capability_policy_builder: Callable[[Any], dict[str, Any]],
        collect_policy_memory_outputs: Callable[[Any, TaskBrief, list[ResultOutput]], list[ResultOutput]],
    ) -> None:
        self.publish_event = publish_event
        self.record_node_event = record_node_event
        self.abort_check = abort_check
        self.load_workspace_data = load_workspace_data
        self.needs_workspace_context = needs_workspace_context
        self.context_requirements_from_brief = context_requirements_from_brief
        self.capability_policy_builder = capability_policy_builder
        self.collect_policy_memory_outputs = collect_policy_memory_outputs
        self._node_harness_metadata: dict[tuple[str, str], dict[str, Any]] = {}

    async def run(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        started_at: datetime,
    ) -> TaskReport:
        try:
            templates = await self._load_templates()
            team_policy = build_capability_team_policy(
                capability,
                templates=templates,
            )
            capability_policy = self.capability_policy_builder(capability)
            required_skill_ids = self._required_team_skill_ids(
                team_policy=team_policy,
                templates=templates,
            )
            skill_catalog = await self._load_skill_catalog() if required_skill_ids else {}
            self._validate_team_preflight(
                capability_policy=capability_policy,
                skill_catalog=skill_catalog,
                required_skill_ids=required_skill_ids,
            )
            context_requirements = self.context_requirements_from_brief(brief)
            workspace_data = (
                await self.load_workspace_data(
                    brief.workspace_id,
                    capability_policy=capability_policy,
                    context_requirements=context_requirements,
                    user_id=brief.user_id,
                )
                if self.needs_workspace_context(capability_policy, context_requirements)
                else {}
            )
            workspace_type = _workspace_type_from_brief_or_capability(brief, capability)
            workspace_map = build_academic_workspace_map_from_workspace_data(
                workspace_id=brief.workspace_id,
                workspace_type=workspace_type,
                workspace_data=workspace_data,
            )
            workspace_map_summary = compact_workspace_map_summary(workspace_map)
            research_brief = build_research_brief(
                execution_id=execution_id,
                workspace_id=brief.workspace_id,
                workspace_type=workspace_type,
                capability_id=brief.capability_id,
                user_objective=brief.raw_message,
                workspace_map=workspace_map_summary,
                capability_metadata={"name": getattr(capability, "display_name", brief.capability_id)},
            )
            workspace_data["academic_workspace_map"] = workspace_map_summary
            workspace_data["research_brief"] = research_brief.model_dump(mode="json")
            blackboard = TeamBlackboard(mission_summary=brief.raw_message or capability.display_name)
            invocations, gates = await self._run_iteration(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
                skill_catalog=skill_catalog,
            )
            if invocations and all(invocation.status == "cancelled" for invocation in invocations):
                return self._cancelled_report(execution_id, brief, started_at)
            duration = int((datetime.now(UTC) - started_at).total_seconds())
            errors = [
                *self._errors_from_invocations(invocations),
                *self._errors_from_quality_gates(gates),
            ]
            status = "failed_partial" if errors else "completed"
            expert_reports = [
                report
                for invocation in invocations
                for report in [expert_report_from_member_output(invocation.output_report)]
                if report is not None
            ]
            review_packet, research_state = build_academic_harness_outputs(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                capability_name=getattr(capability, "display_name", brief.capability_id),
                expert_reports=expert_reports,
                completion_status=status,
                quality_state=[gate.model_dump(mode="json") for gate in gates],
                research_brief=workspace_data.get("research_brief"),
                workspace_map_summary=workspace_data.get("academic_workspace_map"),
            )
            workspace_data["research_state"] = research_state.model_dump(mode="json")
            outputs: list[ResultOutput] = self._mapped_outputs_from_graph_template(
                capability,
                invocations,
            )
            if not outputs:
                outputs = list(self._outputs_from_invocations(invocations))
            if status == "completed":
                outputs.extend(self.collect_policy_memory_outputs(capability, brief, outputs))
            else:
                outputs = self._mark_outputs_unchecked(outputs)
            review_items: list[dict[str, Any]] = []
            if status == "completed":
                review_items.extend(
                    await self._stage_sandbox_artifact_review_items(
                        invocations,
                        brief=brief,
                        execution_id=execution_id,
                    )
                )
                review_items.extend(
                    await self._stage_prism_review_items(
                        capability,
                        invocations,
                        brief=brief,
                        execution_id=execution_id,
                    )
                )
            final_gate_errors = self._errors_from_final_research_evidence(
                TaskReport(
                    execution_id=execution_id,
                    capability_id=brief.capability_id,
                    status=status,
                    duration_seconds=duration,
                    narrative="Final research evidence evaluation.",
                    outputs=outputs,
                    review_items=review_items,
                    review_packet=review_packet,
                    errors=errors,
                ),
                invocations,
                capability_policy=capability_policy,
            )
            if final_gate_errors:
                errors.extend(final_gate_errors)
                status = "failed_partial"
                outputs = self._mark_outputs_unchecked(outputs)
                review_packet = review_packet.model_copy(update={"completion_status": "partial"})
                review_items.extend(
                    self._review_items_from_final_gate_errors(
                        final_gate_errors,
                        execution_id=execution_id,
                    )
                )
            return TaskReport(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                status=status,
                duration_seconds=duration,
                token_usage=self._aggregate_token_usage(invocations),
                narrative=self._build_narrative(
                    capability,
                    invocations,
                    gates,
                    has_errors=bool(errors),
                ),
                outputs=outputs,
                review_items=review_items,
                review_packet=review_packet,
                preview_item_id=self._result_preview_item_id(invocations),
                errors=errors,
            )
        except (TeamPolicyError, CapabilityPreflightError) as exc:
            return self._failed_report(execution_id, brief, started_at, str(exc))
        except Exception as exc:
            logger.exception("team kernel failed", extra={"execution_id": execution_id})
            return self._failed_report(execution_id, brief, started_at, str(exc))
        finally:
            self._clear_node_harness_metadata(execution_id)

    async def _load_templates(self) -> dict[str, AgentTemplate]:
        async with dataservice_client() as client:
            records = await client.list_agent_templates(enabled_only=True)
        return {
            record.id: AgentTemplate.model_validate(record.model_dump(mode="json"))
            for record in records
        }

    async def _load_skill_catalog(self) -> dict[str, Any]:
        async with dataservice_client() as client:
            records = await client.list_catalog_skills(enabled_only=True)
        return {record.id: record for record in records}

    def _validate_team_preflight(
        self,
        *,
        capability_policy: dict[str, Any],
        skill_catalog: dict[str, Any],
        required_skill_ids: set[str],
    ) -> None:
        validate_research_evidence_policy(capability_policy)
        for skill_id in sorted(required_skill_ids):
            if skill_id not in skill_catalog:
                raise CapabilityPreflightError(f"unknown capability skill: {skill_id}")

    def _required_team_skill_ids(
        self,
        *,
        team_policy: CapabilityTeamPolicy,
        templates: dict[str, AgentTemplate],
    ) -> set[str]:
        required_skill_ids = {
            *team_policy.capability_skills,
            *team_policy.contract_overlay_skills,
        }
        for template_id in [*team_policy.core_templates, *team_policy.optional_templates]:
            template = templates[template_id]
            effective_skills = resolve_effective_skills(
                template,
                capability_skills=team_policy.capability_skills or template.default_skills,
            )
            if not effective_skills and template.runtime_defaults.get("allow_skillless") is not True:
                raise CapabilityPreflightError(
                    f"agent template {template_id} must resolve at least one skill "
                    "or set runtime_defaults.allow_skillless=true"
                )
            required_skill_ids.update(effective_skills)
        return required_skill_ids

    async def _run_iteration(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any] | None = None,
        blackboard: TeamBlackboard,
        skill_catalog: dict[str, Any] | None = None,
    ) -> tuple[list[AgentInvocation], list[QualityGateResult]]:
        counts: Counter[str] = Counter()
        invocations: list[AgentInvocation] = []
        gates: list[QualityGateResult] = []
        skill_cache = SkillCatalogCache(
            records=dict(skill_catalog or {}),
            loaded=skill_catalog is not None,
        )
        blackboard.harness_episode = start_harness_episode(
            execution_id=execution_id,
            core_templates=team_policy.core_templates,
        )

        core_invocations = await self._run_core_phase(
            execution_id=execution_id,
            brief=brief,
            capability=capability,
            templates=templates,
            team_policy=team_policy,
            capability_policy=capability_policy,
            workspace_data=workspace_data,
            blackboard=blackboard,
            counts=counts,
            invocations=invocations,
            skill_cache=skill_cache,
        )

        if self._all_cancelled(invocations):
            finish_harness_episode(blackboard.harness_episode, stop_reason="cancelled")
            await self._persist_runtime_state(execution_id, blackboard)
            return invocations, gates
        if not invocations:
            finish_harness_episode(blackboard.harness_episode, stop_reason="no_invocations")
            await self._persist_runtime_state(execution_id, blackboard)
            return invocations, gates

        batch_gates = await self._evaluate_quality_gates(
            execution_id=execution_id,
            team_policy=team_policy,
            capability_policy=capability_policy,
            counts=counts,
            invocations=invocations,
            latest_invocations=core_invocations,
            blackboard=blackboard,
            workspace_data=workspace_data,
        )
        gates.extend(batch_gates)
        next_batch = self._next_recruits_from_gates(
            batch_gates,
            counts,
            len(invocations),
            team_policy,
        )
        self._record_replan_decision(
            blackboard,
            iteration=1,
            phase="core",
            gates=batch_gates,
            selected_recruits=next_batch,
        )
        if not next_batch:
            finish_harness_episode(
                blackboard.harness_episode,
                stop_reason=stop_reason_from_gates(
                    batch_gates,
                    selected_recruits=[],
                ),
            )
            await self._persist_runtime_state(execution_id, blackboard)
            return invocations, gates
        await self._persist_runtime_state(execution_id, blackboard)
        gates.extend(
            await self._run_dynamic_recruitment_phase(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
                counts=counts,
                invocations=invocations,
                skill_cache=skill_cache,
                next_batch=next_batch,
            )
        )

        return invocations, gates

    async def _run_core_phase(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any] | None = None,
        blackboard: TeamBlackboard,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        skill_cache: SkillCatalogCache,
    ) -> list[AgentInvocation]:
        core_waves = self._core_recruitment_waves(
            capability=capability,
            templates=templates,
            team_policy=team_policy,
        )
        core_invocations: list[AgentInvocation] = []
        for current_core in core_waves:
            if len(invocations) >= team_policy.limits.max_invocations_total:
                break
            latest_batch = await self._run_invocation_batch(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
                counts=counts,
                invocations=invocations,
                skill_cache=skill_cache,
                iteration=1,
                recruits=current_core,
            )
            if not latest_batch:
                continue
            core_invocations.extend(latest_batch)
            self._sync_current_harness_evidence(workspace_data, latest_batch)
            self._sync_current_research_state(
                workspace_data,
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                invocations=invocations,
                gates=[],
            )
            if self._all_cancelled(invocations):
                break
        return core_invocations

    def _core_recruitment_waves(
        self,
        *,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
    ) -> list[list[RecruitmentCandidate]]:
        phase_by_template = self._graph_phase_by_core_template(capability, templates, team_policy)
        if not phase_by_template:
            return self._chunk_core_recruits(
                [
                    RecruitmentCandidate(
                        template_id=template_id,
                        reason="core team member for capability",
                    )
                    for template_id in team_policy.core_templates
                ],
                team_policy,
            )

        grouped: dict[int, list[RecruitmentCandidate]] = {}
        for template_id in team_policy.core_templates:
            phase_index = phase_by_template.get(template_id, 0)
            grouped.setdefault(phase_index, []).append(
                RecruitmentCandidate(
                    template_id=template_id,
                    reason="core team member for capability",
                )
            )
        waves: list[list[RecruitmentCandidate]] = []
        for phase_index in sorted(grouped):
            waves.extend(self._chunk_core_recruits(grouped[phase_index], team_policy))
        return waves

    @staticmethod
    def _chunk_core_recruits(
        recruits: list[RecruitmentCandidate],
        team_policy: CapabilityTeamPolicy,
    ) -> list[list[RecruitmentCandidate]]:
        if not recruits:
            return []
        size = max(1, team_policy.limits.max_parallel_invocations)
        return [recruits[index : index + size] for index in range(0, len(recruits), size)]

    @staticmethod
    def _graph_phase_by_core_template(
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
    ) -> dict[str, int]:
        graph_template = getattr(capability, "graph_template", None)
        if not isinstance(graph_template, dict):
            return {}
        phases = graph_template.get("phases")
        if not isinstance(phases, list) or not phases:
            return {}

        phase_by_template: dict[str, int] = {}
        core_template_ids = set(team_policy.core_templates)
        for phase_index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            tasks = phase.get("tasks")
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                matched = _matching_core_template_ids(task, templates, core_template_ids)
                for template_id in matched:
                    phase_by_template.setdefault(template_id, phase_index)
        return phase_by_template

    async def _run_dynamic_recruitment_phase(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        skill_cache: SkillCatalogCache,
        next_batch: list[RecruitmentCandidate],
    ) -> list[QualityGateResult]:
        gates: list[QualityGateResult] = []
        iteration = 2
        no_progress_rounds = 0
        while (
            next_batch
            and iteration <= team_policy.limits.max_iterations
            and len(invocations) < team_policy.limits.max_invocations_total
        ):
            batch = await self._run_invocation_batch(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
                counts=counts,
                invocations=invocations,
                skill_cache=skill_cache,
                iteration=iteration,
                recruits=next_batch[: team_policy.limits.max_parallel_invocations],
            )
            if not batch:
                break
            if self._all_cancelled(invocations):
                finish_harness_episode(blackboard.harness_episode, stop_reason="cancelled")
                await self._persist_runtime_state(execution_id, blackboard)
                break

            batch_gates = await self._evaluate_quality_gates(
                execution_id=execution_id,
                team_policy=team_policy,
                capability_policy=capability_policy,
                counts=counts,
                invocations=invocations,
                latest_invocations=batch,
                blackboard=blackboard,
                workspace_data=workspace_data,
            )
            gates.extend(batch_gates)
            self._sync_current_research_state(
                workspace_data,
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                invocations=invocations,
                gates=gates,
            )
            recruits = self._next_recruits_from_gates(
                batch_gates,
                counts,
                len(invocations),
                team_policy,
            )
            self._record_replan_decision(
                blackboard,
                iteration=iteration,
                phase="dynamic_recruitment",
                gates=batch_gates,
                selected_recruits=recruits,
            )
            if not recruits:
                finish_harness_episode(
                    blackboard.harness_episode,
                    stop_reason=stop_reason_from_gates(
                        batch_gates,
                        selected_recruits=[],
                    ),
                )
                await self._persist_runtime_state(execution_id, blackboard)
                if any(gate.next_action == "recruit_more" for gate in batch_gates):
                    no_progress_rounds += 1
                    if no_progress_rounds >= team_policy.limits.no_progress_rounds_before_stop:
                        break
                break

            no_progress_rounds = 0
            next_batch = recruits
            await self._persist_runtime_state(execution_id, blackboard)
            iteration += 1

        if blackboard.harness_episode is not None and blackboard.harness_episode.status != "finished":
            finish_harness_episode(
                blackboard.harness_episode,
                stop_reason=self._dynamic_stop_reason(
                    iteration=iteration,
                    team_policy=team_policy,
                    invocations=invocations,
                ),
            )
            await self._persist_runtime_state(execution_id, blackboard)
        return gates

    @staticmethod
    def _all_cancelled(invocations: list[AgentInvocation]) -> bool:
        return bool(invocations) and all(
            invocation.status == "cancelled"
            for invocation in invocations
        )

    async def _run_invocation_batch(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        skill_cache: SkillCatalogCache,
        iteration: int,
        recruits: list[RecruitmentCandidate],
    ) -> list[AgentInvocation]:
        batch = self._build_invocation_batch(
            execution_id=execution_id,
            brief=brief,
            capability=capability,
            templates=templates,
            team_policy=team_policy,
            capability_policy=capability_policy,
            blackboard=blackboard,
            workspace_data=workspace_data,
            counts=counts,
            iteration=iteration,
            recruits=recruits,
        )
        invocations.extend(batch)
        if not batch:
            return batch
        skill_load_error: Exception | None = None
        if await self._should_prefetch_skills(execution_id):
            try:
                await self._ensure_skill_cache(skill_cache, batch, team_policy)
            except Exception as exc:
                skill_load_error = exc
        if skill_load_error is None:
            self._inject_quality_contracts(
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                skill_records=skill_cache.records,
                workspace_data=workspace_data,
                invocations=batch,
            )
        await asyncio.gather(
            *[
                self._run_invocation(
                    invocation=invocation,
                    template=templates[invocation.template_id],
                    capability_policy=capability_policy,
                    workspace_data=workspace_data or {},
                    blackboard=blackboard,
                    skill_records=skill_cache.records,
                    skill_load_error=skill_load_error,
                )
                for invocation in batch
            ]
        )
        self._sync_invocation_outputs_to_blackboard(blackboard, batch)
        return batch

    @staticmethod
    def _sync_harness_replan_signals(
        blackboard: TeamBlackboard,
        latest_invocations: list[AgentInvocation],
    ) -> list[dict[str, Any]]:
        latest_signals: list[dict[str, Any]] = []
        for invocation in latest_invocations:
            for signal in build_harness_replan_signals_from_tool_calls(invocation.tool_calls):
                enriched = dict(signal)
                enriched["source_invocation_id"] = invocation.id
                enriched["source_template_id"] = invocation.template_id
                enriched["source_display_name"] = invocation.display_name
                latest_signals.append(enriched)
        if not latest_signals:
            return []
        existing = {
            _replan_signal_key(signal)
            for signal in blackboard.harness_replan_signals
        }
        for signal in latest_signals:
            key = _replan_signal_key(signal)
            if key in existing:
                continue
            blackboard.harness_replan_signals.append(signal)
            existing.add(key)
        return latest_signals

    def _sync_current_harness_evidence(
        self,
        workspace_data: dict[str, Any],
        latest_invocations: list[AgentInvocation],
    ) -> None:
        entries: list[dict[str, Any]] = []
        for invocation in latest_invocations:
            cached_harness = self._node_harness_metadata.get(
                (invocation.execution_id or "", invocation.id),
            )
            tool_metadata = build_harness_node_metadata_from_tool_calls(invocation.tool_calls)
            merged_harness: dict[str, Any] = {}
            if isinstance(tool_metadata, dict) and isinstance(tool_metadata.get("harness"), dict):
                _merge_non_empty_harness(merged_harness, tool_metadata["harness"])
            if isinstance(cached_harness, dict):
                _merge_non_empty_harness(merged_harness, cached_harness)
            if not _has_replayable_harness_evidence(merged_harness):
                continue
            harness_metadata = {"harness": merged_harness} if merged_harness else None
            if not harness_metadata:
                continue
            entries.append(
                {
                    "execution_id": invocation.execution_id or "",
                    "node_id": invocation.id,
                    "display_name": invocation.display_name,
                    "template_id": invocation.template_id,
                    "node_metadata": harness_metadata,
                }
            )
        if not entries:
            return

        history = workspace_data.get("workspace_history")
        history = history if isinstance(history, dict) else None
        if history is not None:
            current = history.get("recent_executions")
            current = current if isinstance(current, list) else []
            history["recent_executions"] = _prepend_current_harness_evidence(entries, current)
            workspace_data["workspace_history"] = history
            return

        current = workspace_data.get("recent_executions")
        current = current if isinstance(current, list) else []
        workspace_data["recent_executions"] = _prepend_current_harness_evidence(entries, current)

    @staticmethod
    def _sync_current_research_state(
        workspace_data: dict[str, Any],
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        invocations: list[AgentInvocation],
        gates: list[QualityGateResult],
    ) -> None:
        expert_reports = [
            report
            for invocation in invocations
            for report in [expert_report_from_member_output(invocation.output_report)]
            if report is not None
        ]
        if not expert_reports:
            return
        research_state = compact_research_state(
            execution_id=execution_id,
            goal=getattr(capability, "display_name", brief.capability_id),
            expert_reports=[report.model_dump(mode="json") for report in expert_reports],
            quality_state=[gate.model_dump(mode="json") for gate in gates],
            research_brief=workspace_data.get("research_brief"),
            workspace_map_summary=workspace_data.get("academic_workspace_map"),
        )
        workspace_data["research_state"] = research_state.model_dump(mode="json")

    def _sync_invocation_outputs_to_blackboard(
        self,
        blackboard: TeamBlackboard,
        latest_invocations: list[AgentInvocation],
    ) -> None:
        existing = {
            str(item.get("source_invocation_id") or "")
            for item in blackboard.evidence_items
            if isinstance(item, dict)
        }
        for invocation in latest_invocations:
            if invocation.status != "succeeded" or not invocation.output_report:
                continue
            if invocation.id in existing:
                continue
            if self._output_has_accumulating_blackboard_fields(invocation.output_report):
                continue
            evidence = self._blackboard_evidence_from_invocation(invocation)
            if not evidence:
                continue
            blackboard.evidence_items.append(evidence)
            existing.add(invocation.id)

    @staticmethod
    def _output_has_accumulating_blackboard_fields(output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        return any(
            isinstance(output.get(field_name), list) and bool(output.get(field_name))
            for field_name in BLACKBOARD_ACCUMULATING_FIELDS
        )

    def _blackboard_evidence_from_invocation(
        self,
        invocation: AgentInvocation,
    ) -> dict[str, Any]:
        output = invocation.output_report if isinstance(invocation.output_report, dict) else {}
        evidence: dict[str, Any] = {
            "source_invocation_id": invocation.id,
            "source_template_id": invocation.template_id,
            "source_display_name": invocation.display_name,
            "kind": "team_member_output",
        }
        papers = output.get("papers")
        if isinstance(papers, list) and papers:
            evidence["kind"] = "source_search_results"
            evidence["paper_count"] = len(papers)
            evidence["papers"] = [_bounded_paper_item(item) for item in papers[:12] if isinstance(item, dict)]
        preview = self._preview_output(output)
        if preview:
            evidence["preview"] = preview[:1200]
        return evidence if len(evidence) > 4 else {}

    def _inject_quality_contracts(
        self,
        *,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        skill_records: dict[str, Any | None],
        workspace_data: dict[str, Any],
        invocations: list[AgentInvocation],
    ) -> None:
        for invocation in invocations:
            invocation.input_brief["quality_contract"] = QualityContractResolver.resolve(
                capability=capability,
                template=templates[invocation.template_id],
                team_policy=team_policy,
                effective_skill_ids=invocation.effective_skills,
                skill_records=skill_records,
                workspace_data=workspace_data,
            ).model_dump(mode="json")

    async def _should_prefetch_skills(self, execution_id: str) -> bool:
        try:
            return not await self.abort_check(execution_id)
        except Exception:
            return False

    async def _ensure_skill_cache(
        self,
        skill_cache: SkillCatalogCache,
        invocations: list[AgentInvocation],
        team_policy: CapabilityTeamPolicy,
    ) -> None:
        missing: list[str] = []
        for invocation in invocations:
            for skill_id in invocation.effective_skills:
                if skill_id not in skill_cache.records and skill_id not in missing:
                    missing.append(skill_id)
        for skill_id in team_policy.contract_overlay_skills:
            if skill_id not in skill_cache.records and skill_id not in missing:
                missing.append(skill_id)
        if not missing:
            return
        if not skill_cache.loaded:
            skill_cache.records.update(await self._load_skill_catalog())
            skill_cache.loaded = True
        for skill_id in missing:
            skill_cache.records.setdefault(skill_id, None)

    async def _evaluate_quality_gates(
        self,
        *,
        execution_id: str,
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        counts: Counter[str],
        invocations: list[AgentInvocation],
        latest_invocations: list[AgentInvocation],
        blackboard: TeamBlackboard,
        workspace_data: dict[str, Any],
    ) -> list[QualityGateResult]:
        self._sync_current_harness_evidence(workspace_data, latest_invocations)
        gates = self._run_quality_gates(
            team_policy.quality_pipeline,
            invocations,
            team_policy=team_policy,
            capability_policy=capability_policy,
            counts=counts,
            latest_invocations=latest_invocations,
            harness_replan_signals=self._sync_harness_replan_signals(
                blackboard,
                latest_invocations,
            ),
        )
        blackboard.quality_gate_history.extend(
            gate.model_dump(mode="json") for gate in gates
        )
        for gate in gates:
            await self._safe_publish_team_event(
                execution_id,
                "execution.team.quality_gate",
                {"quality_gate": gate.model_dump(mode="json")},
            )
        return gates

    async def _persist_runtime_state(
        self,
        execution_id: str,
        blackboard: TeamBlackboard,
    ) -> None:
        if not blackboard.quality_gate_history and not blackboard.harness_episode:
            return
        try:
            async with dataservice_client() as client:
                update_execution = getattr(client, "update_execution", None)
                if not callable(update_execution):
                    return
                runtime_state: dict[str, Any] = {}
                get_execution = getattr(client, "get_execution", None)
                if callable(get_execution):
                    record = await get_execution(execution_id)
                    existing = getattr(record, "runtime_state_json", None)
                    if isinstance(existing, dict):
                        runtime_state.update(existing)
                runtime_state["quality_gates"] = list(blackboard.quality_gate_history)
                if blackboard.harness_episode:
                    runtime_state["harness_episode"] = bounded_harness_episode(
                        blackboard.harness_episode,
                    )
                await update_execution(
                    execution_id,
                    ExecutionUpdatePayload(runtime_state_json=runtime_state),
                )
        except Exception:
            logger.warning("Failed to persist team quality gate runtime state", exc_info=True)

    @staticmethod
    def _record_replan_decision(
        blackboard: TeamBlackboard,
        *,
        iteration: int,
        phase: str,
        gates: list[QualityGateResult],
        selected_recruits: list[RecruitmentCandidate],
    ) -> None:
        record_replan_decision(
            blackboard.harness_episode,
            iteration=iteration,
            phase=phase,
            gates=gates,
            selected_recruits=[recruit.template_id for recruit in selected_recruits],
        )

    @staticmethod
    def _dynamic_stop_reason(
        *,
        iteration: int,
        team_policy: CapabilityTeamPolicy,
        invocations: list[AgentInvocation],
    ) -> str:
        if len(invocations) >= team_policy.limits.max_invocations_total:
            return "max_invocations_reached"
        if iteration > team_policy.limits.max_iterations:
            return "max_iterations_reached"
        return "dynamic_recruitment_stopped"

    def _build_invocation_batch(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: CapabilityTeamPolicy,
        capability_policy: dict[str, Any],
        blackboard: TeamBlackboard,
        workspace_data: dict[str, Any] | None = None,
        counts: Counter[str],
        iteration: int,
        recruits: list[RecruitmentCandidate],
    ) -> list[AgentInvocation]:
        batch: list[AgentInvocation] = []
        workspace_data = workspace_data or {}
        for recruit in recruits:
            template_id = recruit.template_id
            if not self._can_invoke_template(
                template_id,
                counts,
                total_invocations=counts.total(),
                team_policy=team_policy,
            ):
                continue
            template = templates[template_id]
            counts[template_id] += 1
            effective_tools = resolve_effective_tools(template, team_policy)
            effective_skills = resolve_effective_skills(
                template,
                capability_skills=team_policy.capability_skills or template.default_skills,
            )
            invocation = build_invocation_assignment(
                template=template,
                iteration=iteration,
                template_invocation_count=counts[template_id],
                reason=recruit.reason,
                input_brief=self._build_member_brief(
                    brief,
                    capability,
                    template,
                    blackboard,
                    capability_policy=capability_policy,
                    workspace_data=workspace_data,
                ),
                effective_tools=effective_tools,
                effective_skills=effective_skills,
                profile_override=team_policy.template_profile_overrides.get(template_id),
            )
            invocation.execution_id = execution_id
            batch.append(invocation)
        return batch

    def _build_member_brief(
        self,
        brief: TaskBrief,
        capability: Any,
        template: AgentTemplate,
        blackboard: TeamBlackboard,
        *,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
    ) -> dict[str, Any]:
        return build_team_member_context(
            brief=brief,
            capability_name=getattr(capability, "display_name", brief.capability_id),
            template_id=template.id,
            display_role=template.display_role,
            blackboard=blackboard,
            capability_policy=capability_policy,
            research_state=workspace_data.get("research_state"),
            research_brief=workspace_data.get("research_brief"),
            workspace_map_summary=workspace_data.get("academic_workspace_map"),
        )

    async def _run_invocation(
        self,
        *,
        invocation: AgentInvocation,
        template: AgentTemplate,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
        skill_records: dict[str, Any | None],
        skill_load_error: Exception | None,
    ) -> None:
        started_at = datetime.now(UTC)
        invocation.status = "running"
        await self._safe_record_invocation(invocation, status="running", started_at=started_at)
        await self._safe_publish_team_event(
            invocation.execution_id or "",
            "execution.team.invocation",
            {"invocation": invocation.model_dump(mode="json")},
        )
        try:
            if await self.abort_check(invocation.execution_id or ""):
                invocation.status = "cancelled"
            else:
                if skill_load_error is not None:
                    raise skill_load_error
                skill = skill_records.get(invocation.effective_skills[0]) if invocation.effective_skills else None
                subagent_type = getattr(skill, "subagent_type", None) or "react"
                subagent_cls = REGISTRY.get(subagent_type)

                async def emit_expert_snapshot(snapshot: dict[str, Any]) -> None:
                    snapshots = sanitize_expert_snapshot_items([snapshot])
                    if not snapshots:
                        return
                    invocation.expert_snapshots = [
                        *invocation.expert_snapshots,
                        *snapshots,
                    ][-20:]
                    await self._safe_record_invocation(invocation, status="running")
                    await self._safe_publish_team_event(
                        invocation.execution_id or "",
                        "execution.team.expert_snapshot",
                        {
                            "invocation_id": invocation.id,
                            "snapshot": snapshots[-1],
                        },
                    )

                async def safe_publish_event(
                    execution_id: str,
                    event_name: str,
                    payload: dict[str, Any],
                ) -> None:
                    await self._safe_publish_team_event(execution_id, event_name, payload)

                ctx = SubagentContext(
                    workspace_id=str(invocation.input_brief.get("workspace_id") or ""),
                    execution_id=invocation.execution_id or "",
                    prompt=template.persona_prompt,
                    inputs=invocation.input_brief,
                    tools=invocation.effective_tools,
                    workspace_data=workspace_data,
                    capability_policy=capability_policy,
                    skill=skill,
                    team_context=blackboard.model_dump(mode="json"),
                    invocation=invocation.model_dump(mode="json"),
                    publish_event=safe_publish_event,
                    expert_snapshot_emitter=emit_expert_snapshot,
                )
                result: SubagentResult = await _run_subagent_with_timeout(
                    subagent_cls().run(ctx),
                    timeout_seconds=_invocation_timeout_seconds(
                        capability_policy=capability_policy,
                        skill=skill,
                    ),
                    invocation_id=invocation.id,
                )
                invocation.status = "succeeded"
                invocation.output_report = result.output
                invocation.tool_calls = result.tool_calls or []
                invocation.token_usage = result.token_usage
                result_metadata = result.metadata if isinstance(result.metadata, dict) else {}
                invocation.expert_snapshots = merge_expert_snapshot_items(
                    invocation.expert_snapshots,
                    list(result_metadata.get("expert_snapshots") or []),
                )
                invocation.expert_preview_items = merge_expert_preview_items(
                    invocation.expert_preview_items,
                    list(result_metadata.get("expert_preview_items") or []),
                )
                if not invocation.expert_preview_items:
                    preview_item = build_expert_output_preview_item(
                        invocation,
                        summary=self._preview_output(result.output),
                    )
                    if preview_item:
                        invocation.expert_preview_items = [preview_item]
                self._merge_output_into_blackboard(blackboard, result.output)
                blackboard.latest_leader_summary = self._preview_output(result.output)
        except Exception as exc:
            invocation.status = "failed"
            invocation.error = {"message": str(exc)}
            structured_output = _exception_output_with_tool_calls(exc)
            if structured_output is not None:
                invocation.output_report = structured_output
                invocation.tool_calls = [
                    dict(tool_call)
                    for tool_call in structured_output.get("tool_calls") or []
                    if isinstance(tool_call, dict)
                ]
        completed_at = datetime.now(UTC)
        invocation.completed_at = completed_at
        await self._safe_record_invocation(
            invocation,
            status=invocation.status,
            completed_at=completed_at,
        )
        await self._safe_publish_team_event(
            invocation.execution_id or "",
            "execution.team.invocation",
            {"invocation": invocation.model_dump(mode="json")},
        )

    async def _safe_record_invocation(
        self,
        invocation: AgentInvocation,
        *,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        try:
            await self._record_invocation(
                invocation,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
            )
        except Exception:
            logger.warning("Failed to record team invocation node", exc_info=True)

    async def _safe_publish_team_event(
        self,
        execution_id: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await self.publish_event(execution_id, event_name, payload)
        except Exception:
            logger.warning("Failed to publish team event %s", event_name, exc_info=True)

    async def _record_invocation(
        self,
        invocation: AgentInvocation,
        *,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        node_metadata = {
            "team": True,
            "template_id": invocation.template_id,
            "display_name": invocation.display_name,
            "assigned_role": invocation.assigned_role,
            "recruitment_reason": invocation.recruitment_reason,
            "effective_tools": invocation.effective_tools,
            "effective_skills": invocation.effective_skills,
            "expert_profile": invocation.expert_profile,
        }
        harness_metadata = build_harness_node_metadata_from_tool_calls(invocation.tool_calls)
        if harness_metadata:
            node_metadata.update(harness_metadata)
        node_key = (invocation.execution_id or "", invocation.id)
        cached_harness = dict(self._node_harness_metadata.get(node_key) or {})
        tool_harness = (
            node_metadata.get("harness")
            if isinstance(node_metadata.get("harness"), dict)
            else None
        )
        if tool_harness:
            cached_harness.update(tool_harness)
        node_metadata["harness"] = build_expert_node_metadata(
            invocation,
            status=status,
            existing_harness=cached_harness,
        )
        self._node_harness_metadata[node_key] = dict(node_metadata["harness"])

        await self.record_node_event(
            execution_id=invocation.execution_id or "",
            node_id=invocation.id,
            node_type="agent_invocation",
            label=invocation.display_name,
            status="completed" if status == "succeeded" else status,
            input_data=invocation.input_brief,
            output_data=invocation.output_report,
            tool_calls=invocation.tool_calls,
            token_usage=invocation.token_usage,
            error=invocation.error["message"] if invocation.error else None,
            node_metadata=node_metadata,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _clear_node_harness_metadata(self, execution_id: str) -> None:
        for key in list(self._node_harness_metadata):
            if key[0] == execution_id:
                del self._node_harness_metadata[key]

    def _can_invoke_template(
        self,
        template_id: str,
        counts: Counter[str],
        total_invocations: int,
        team_policy: CapabilityTeamPolicy,
    ) -> bool:
        if total_invocations >= team_policy.limits.max_invocations_total:
            return False
        return counts[template_id] < team_policy.limits.max_invocations_per_template

    def _next_recruits_from_gates(
        self,
        gates: list[QualityGateResult],
        counts: Counter[str],
        total_invocations: int,
        team_policy: CapabilityTeamPolicy,
    ) -> list[RecruitmentCandidate]:
        recruits: list[RecruitmentCandidate] = []
        seen: set[str] = set()
        remaining_total = team_policy.limits.max_invocations_total - total_invocations
        if remaining_total <= 0:
            return recruits
        batch_limit = min(team_policy.limits.max_parallel_invocations, remaining_total)
        for gate in gates:
            if gate.next_action not in {"recruit_more", "revise_existing"}:
                continue
            for item in gate.suggested_recruits:
                template_id = str(item.get("template_id") or "")
                if not template_id or template_id in seen:
                    continue
                if not self._is_recruitable_template(template_id, team_policy):
                    continue
                if not self._can_invoke_template(
                    template_id,
                    counts,
                    total_invocations + len(recruits),
                    team_policy,
                ):
                    continue
                reason = str(item.get("reason") or gate.gate_id)
                recruits.append(
                    RecruitmentCandidate(
                        template_id=template_id,
                        reason=f"quality gate requested: {reason}",
                    )
                )
                seen.add(template_id)
                if len(recruits) >= batch_limit:
                    return recruits
        return recruits

    def _is_recruitable_template(self, template_id: str, team_policy: CapabilityTeamPolicy) -> bool:
        return template_id in {*team_policy.core_templates, *team_policy.optional_templates}

    def _run_quality_gates(
        self,
        quality_pipeline: list[str],
        invocations: list[AgentInvocation],
        *,
        team_policy: CapabilityTeamPolicy | None = None,
        capability_policy: dict[str, Any] | None = None,
        counts: Counter[str] | None = None,
        latest_invocations: list[AgentInvocation] | None = None,
        harness_replan_signals: list[dict[str, Any]] | None = None,
    ) -> list[QualityGateResult]:
        return evaluate_quality_gates(
            quality_pipeline,
            invocations,
            team_policy=team_policy,
            capability_policy=capability_policy,
            counts=counts,
            latest_invocations=latest_invocations,
            harness_replan_signals=harness_replan_signals,
        )

    def _outputs_from_invocations(self, invocations: list[AgentInvocation]) -> list[DocumentOutput]:
        outputs: list[DocumentOutput] = []
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            content = self._preview_output(invocation.output_report)
            if not content:
                continue
            outputs.append(
                DocumentOutput(
                    id=f"team-output-{invocation.id}",
                    kind="document",
                    preview=f"{invocation.display_name}: {content[:80]}",
                    default_checked=False,
                    data=DocumentData(
                        name=f"{invocation.display_name}内部诊断.md",
                        doc_kind="team_diagnostic_report",
                        content=content,
                    ),
                )
            )
        return outputs

    @staticmethod
    def _merge_output_into_blackboard(blackboard: TeamBlackboard, output: Any) -> None:
        if not isinstance(output, dict):
            return
        for field_name in BLACKBOARD_ACCUMULATING_FIELDS:
            value = output.get(field_name)
            if not isinstance(value, list) or not value:
                continue
            target = getattr(blackboard, field_name)
            seen = {
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                for item in target
            }
            for item in value:
                if not isinstance(item, dict):
                    continue
                key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen:
                    continue
                target.append(item)
                seen.add(key)

    def _mapped_outputs_from_graph_template(
        self,
        capability: Any,
        invocations: list[AgentInvocation],
    ) -> list[ResultOutput]:
        graph_template = getattr(capability, "graph_template", None)
        if not isinstance(graph_template, dict):
            return []
        node_results = self._node_results_for_graph_outputs(graph_template, invocations)
        if not node_results:
            return []
        return OutputMappingResolver().resolve(graph_template, node_results)

    def _node_results_for_graph_outputs(
        self,
        graph_template: dict[str, Any],
        invocations: list[AgentInvocation],
    ) -> dict[str, dict[str, Any]]:
        node_results: dict[str, dict[str, Any]] = {}
        for phase in graph_template.get("phases") or []:
            for task in phase.get("tasks") or []:
                if not task.get("outputs"):
                    continue
                output = self._output_for_graph_task(task, invocations)
                if output is not None:
                    node_results[str(task["name"])] = {"output": output}
        return node_results

    async def _stage_sandbox_artifact_review_items(
        self,
        invocations: list[AgentInvocation],
        *,
        brief: TaskBrief,
        execution_id: str,
    ) -> list[dict[str, Any]]:
        """Register team harness sandbox artifacts through the existing review flow."""

        candidates = collect_sandbox_artifact_candidates(
            {
                invocation.id: {"tool_calls": invocation.tool_calls}
                for invocation in invocations
            }
        )
        if not candidates:
            return []
        try:
            async with dataservice_client() as client:
                for candidate in candidates:
                    asset = await client.register_asset(
                        workspace_asset_payload_for_candidate(
                            workspace_id=brief.workspace_id,
                            execution_id=execution_id,
                            candidate=candidate,
                        )
                    )
                    await client.register_sandbox_artifact(
                        sandbox_artifact_payload_for_candidate(
                            workspace_id=brief.workspace_id,
                            execution_id=execution_id,
                            workspace_asset_id=str(asset.id),
                            candidate=candidate,
                        )
                    )
                items = await client.list_review_items(
                    workspace_id=brief.workspace_id,
                    execution_id=execution_id,
                    target_domain="sandbox",
                    target_kind="sandbox_artifact",
                )
                return [
                    sandbox_review_item_projection(item, execution_id=execution_id)
                    for item in items
                ]
        except Exception:
            logger.warning("Failed to stage team sandbox artifact review items", exc_info=True)
            return []

    async def _stage_prism_review_items(
        self,
        capability: Any,
        invocations: list[AgentInvocation],
        *,
        brief: TaskBrief,
        execution_id: str,
    ) -> list[dict[str, Any]]:
        """Register team manuscript edits through the canonical Prism review flow."""

        manuscript_context = brief.manuscript_context
        if not isinstance(manuscript_context, dict):
            return []
        latex_project_id = str(manuscript_context.get("latex_project_id") or "").strip()
        if not latex_project_id:
            return []
        graph_template = getattr(capability, "graph_template", None)
        if not isinstance(graph_template, dict):
            return []
        node_results = self._node_results_for_graph_outputs(graph_template, invocations)
        if not node_results:
            return []

        default_path = str(manuscript_context.get("main_file") or "main.tex").strip() or "main.tex"
        commands = []
        for phase in graph_template.get("phases") or []:
            for task in phase.get("tasks") or []:
                task_name = str(task.get("name") or "").strip()
                node_result = node_results.get(task_name)
                output = node_result.get("output") if isinstance(node_result, dict) else None
                if not task_name or not isinstance(output, dict):
                    continue
                for decl in task.get("outputs") or []:
                    if not isinstance(decl, dict) or decl.get("kind") != "prism_file_change":
                        continue
                    command = build_prism_file_change_command(
                        decl,
                        output,
                        workspace_id=brief.workspace_id,
                        latex_project_id=latex_project_id,
                        task_name=task_name,
                        execution_id=execution_id,
                        default_path=default_path,
                    )
                    if command is not None:
                        commands.append(command)
        if not commands:
            return []

        try:
            async with dataservice_client() as client:
                for command in commands:
                    await client.upsert_pending_prism_file_change(command)
                items = await client.list_review_items(
                    workspace_id=brief.workspace_id,
                    execution_id=execution_id,
                    target_domain="prism",
                    target_kind="prism_file_change",
                )
                return [
                    prism_review_item_projection(item, execution_id=execution_id)
                    for item in items
                ]
        except Exception:
            logger.warning("Failed to stage team Prism review items", exc_info=True)
            return []

    def _output_for_graph_task(
        self,
        task: dict[str, Any],
        invocations: list[AgentInvocation],
    ) -> dict[str, Any] | None:
        matches = [
            invocation
            for invocation in invocations
            if invocation.status == "succeeded"
            and self._invocation_matches_graph_task(invocation, task)
            and _has_meaningful_output(invocation.output_report)
        ]
        if matches:
            latest = max(
                matches,
                key=lambda item: (
                    int(item.iteration or 0),
                    self._invocation_completed_at(item),
                    item.id,
                ),
            )
            return latest.output_report
        if self._task_declares_document_output(task):
            content = self._aggregate_team_content(invocations)
            return {"text": content} if content else None
        return None

    def _invocation_matches_graph_task(
        self,
        invocation: AgentInvocation,
        task: dict[str, Any],
    ) -> bool:
        template_id = str(
            task.get("agent_template_id") or task.get("template_id") or ""
        ).strip()
        if template_id:
            return invocation.template_id == template_id
        skill_id = str(task.get("skill_id") or "").strip()
        if skill_id and skill_id in invocation.effective_skills:
            return True
        task_name = str(task.get("name") or "").strip()
        normalized_task_name = task_name.replace("-", "_")
        template_name = invocation.template_id.split(".")[0].replace("-", "_")
        return bool(normalized_task_name and normalized_task_name == template_name)

    @staticmethod
    def _invocation_completed_at(invocation: AgentInvocation) -> datetime:
        completed_at = getattr(invocation, "completed_at", None)
        if isinstance(completed_at, datetime):
            if completed_at.tzinfo is None:
                return completed_at.replace(tzinfo=UTC)
            return completed_at
        return datetime.min.replace(tzinfo=UTC)

    @staticmethod
    def _task_declares_document_output(task: dict[str, Any]) -> bool:
        return any(
            isinstance(decl, dict) and decl.get("kind") == "document"
            for decl in task.get("outputs") or []
        )

    def _aggregate_team_content(self, invocations: list[AgentInvocation]) -> str:
        sections: list[str] = []
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            content = self._preview_output(invocation.output_report).strip()
            if not content:
                continue
            sections.append(f"## {invocation.display_name}\n\n{content}")
        return "\n\n".join(sections)

    @staticmethod
    def _result_preview_item_id(invocations: list[AgentInvocation]) -> str | None:
        candidates: list[dict[str, Any]] = []
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            candidates.extend(
                item
                for item in sanitize_expert_preview_items(invocation.expert_preview_items)
                if item.get("preview_item_id")
            )
        if not candidates:
            return None
        ready = [
            item
            for item in candidates
            if str(item.get("status") or "").strip().lower() in {"ready", "saved"}
        ]
        selected = (ready or candidates)[-1]
        return str(selected.get("preview_item_id") or "") or None

    def _errors_from_invocations(self, invocations: list[AgentInvocation]) -> list[ResultError]:
        errors: list[ResultError] = []
        for invocation in invocations:
            if invocation.status not in {"failed", "cancelled"}:
                continue
            message = (
                invocation.error.get("message")
                if isinstance(invocation.error, dict)
                else None
            )
            errors.append(
                ResultError(
                    phase=invocation.assigned_role,
                    task=invocation.template_id,
                    error=message or f"team member {invocation.status}",
                )
            )
        return errors

    def _errors_from_quality_gates(self, gates: list[QualityGateResult]) -> list[ResultError]:
        errors: list[ResultError] = []
        for gate in gates:
            if gate.status != "fail":
                continue
            if gate.next_action not in {"stop_with_warning", "ask_user"} and gate.severity != "high":
                continue
            errors.append(
                ResultError(
                    phase="quality_gate",
                    task=gate.gate_id,
                    error=self._preview_output(gate.model_dump(mode="json")),
                )
            )
        return errors

    def _errors_from_final_research_evidence(
        self,
        report: TaskReport,
        invocations: list[AgentInvocation],
        *,
        capability_policy: dict[str, Any] | None,
    ) -> list[ResultError]:
        surfaces = tuple(
            surface
            for surface in required_surfaces_from_capability_policy(capability_policy, default=())
            if surface in FINAL_REPORT_RESEARCH_EVIDENCE_SURFACES
        )
        if not surfaces:
            return []
        evaluation = evaluate_research_task_evidence(
            report,
            node_events=self._node_events_from_invocations(invocations),
            required_surfaces=surfaces,
        )
        if evaluation.status == "pass":
            return []
        return [
            ResultError(
                phase="final_research_evidence",
                task=str(finding.get("surface") or "research_evidence"),
                error=str(finding.get("message") or "Final research evidence gate failed."),
            )
            for finding in evaluation.findings
        ]

    @staticmethod
    def _review_items_from_final_gate_errors(
        errors: list[ResultError],
        *,
        execution_id: str,
    ) -> list[dict[str, Any]]:
        review_items: list[dict[str, Any]] = []
        for index, error in enumerate(errors):
            surface = str(error.task or "research_evidence").strip() or "research_evidence"
            message = str(error.error or "Final research evidence gate failed.").strip()
            item_id = f"final-gate-{_safe_review_item_id(surface)}-{index}"
            review_items.append(
                {
                    "id": item_id,
                    "kind": "warning",
                    "title": "科研质量门未通过",
                    "summary": message,
                    "status": "blocked",
                    "source": {
                        "phase": "final_research_evidence",
                        "execution_id": execution_id,
                        "surface": surface,
                    },
                    "target": {
                        "kind": "research_evidence_gate",
                        "surface": surface,
                    },
                    "preview": {
                        "format": "text",
                        "excerpt": message[:500],
                    },
                    "risk": {
                        "level": "high",
                        "reasons": [message],
                    },
                    "quality_surfaces": [surface],
                    "default_checked": False,
                    "can_commit": False,
                }
            )
        return review_items

    @staticmethod
    def _node_events_from_invocations(invocations: list[AgentInvocation]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for invocation in invocations:
            node_metadata = build_harness_node_metadata_from_tool_calls(invocation.tool_calls)
            if not node_metadata:
                continue
            events.append(
                {
                    "node_type": "agent_invocation",
                    "status": "completed" if invocation.status == "succeeded" else invocation.status,
                    "node_metadata": {
                        "template_id": invocation.template_id,
                        "display_name": invocation.display_name,
                        **node_metadata,
                    },
                }
            )
        return events

    def _build_narrative(
        self,
        capability: Any,
        invocations: list[AgentInvocation],
        gates: list[QualityGateResult],
        *,
        has_errors: bool = False,
    ) -> str:
        names = "、".join(item.display_name for item in invocations)
        warnings = sum(1 for gate in gates if gate.status != "pass")
        if has_errors:
            failed = sum(1 for item in invocations if item.status in {"failed", "cancelled"})
            gate_text = f"，{warnings} 个质量门未通过" if warnings else ""
            member_text = f"，团队成员：{names}" if names else ""
            return f"未能完成 {capability.display_name}{member_text}，{failed} 个成员未完成{gate_text}。"
        suffix = f"，{warnings} 个质量门需要注意" if warnings else "，质量门已通过"
        return f"完成 {capability.display_name}，团队成员：{names}{suffix}。"

    def _aggregate_token_usage(self, invocations: list[AgentInvocation]) -> dict[str, int] | None:
        usage = {"input": 0, "output": 0}
        for invocation in invocations:
            token_usage = invocation.token_usage or {}
            usage["input"] += int(token_usage.get("input", token_usage.get("input_tokens", 0)) or 0)
            usage["output"] += int(token_usage.get("output", token_usage.get("output_tokens", 0)) or 0)
        return usage if usage["input"] or usage["output"] else None

    def _failed_report(
        self,
        execution_id: str,
        brief: TaskBrief,
        started_at: datetime,
        error: str,
    ) -> TaskReport:
        return TaskReport(
            execution_id=execution_id,
            capability_id=brief.capability_id,
            status="failed_partial",
            duration_seconds=int((datetime.now(UTC) - started_at).total_seconds()),
            narrative=f"团队执行未能完成：{error}",
            outputs=[],
            errors=[ResultError(phase="team_kernel", task="team_kernel", error=error)],
        )

    def _cancelled_report(
        self,
        execution_id: str,
        brief: TaskBrief,
        started_at: datetime,
    ) -> TaskReport:
        return TaskReport(
            execution_id=execution_id,
            capability_id=brief.capability_id,
            status="cancelled",
            duration_seconds=int((datetime.now(UTC) - started_at).total_seconds()),
            narrative="团队执行已取消。",
            outputs=[],
            errors=[],
        )

    @staticmethod
    def _preview_output(output: Any) -> str:
        if isinstance(output, dict):
            for key in ("summary", "report_markdown", "markdown", "text"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if not _has_meaningful_output(output):
                return ""
            return json.dumps(output, ensure_ascii=False, sort_keys=True)
        return str(output or "")

    @staticmethod
    def _mark_outputs_unchecked(outputs: list[ResultOutput]) -> list[ResultOutput]:
        return [
            output.model_copy(update={"default_checked": False})
            for output in outputs
        ]


async def _run_subagent_with_timeout(
    awaitable: Awaitable[SubagentResult],
    *,
    timeout_seconds: float,
    invocation_id: str,
) -> SubagentResult:
    task = asyncio.create_task(awaitable)
    done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
    if task in done:
        return task.result()

    task.cancel()
    task.add_done_callback(_consume_timed_out_subagent_task)
    raise TimeoutError(
        f"Subagent invocation {invocation_id} timed out after {timeout_seconds:.0f}s"
    )


def _consume_timed_out_subagent_task(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.debug("Timed-out subagent task finished with error", exc_info=True)


def _exception_output_with_tool_calls(exc: Exception) -> dict[str, Any] | None:
    output = getattr(exc, "output", None)
    if not isinstance(output, dict):
        return None
    tool_calls = [tool_call for tool_call in output.get("tool_calls") or [] if isinstance(tool_call, dict)]
    if not tool_calls:
        return None
    structured_output = dict(output)
    structured_output["tool_calls"] = [dict(tool_call) for tool_call in tool_calls]
    return structured_output


def _invocation_timeout_seconds(
    *,
    capability_policy: dict[str, Any],
    skill: Any | None,
) -> float:
    configured = None
    limits = capability_policy.get("limits") if isinstance(capability_policy, dict) else None
    if isinstance(limits, dict):
        configured = limits.get("react_timeout_seconds") or limits.get("timeout_seconds")
    if configured is None and isinstance(capability_policy, dict):
        sandbox_policy = capability_policy.get("sandbox_policy")
        if isinstance(sandbox_policy, dict):
            configured = sandbox_policy.get("react_timeout_seconds") or sandbox_policy.get("timeout_seconds")
            resource_limits = sandbox_policy.get("resource_limits")
            if configured is None and isinstance(resource_limits, dict):
                configured = resource_limits.get("react_timeout_seconds")
    if configured is None and skill is not None:
        skill_config = getattr(skill, "config", None)
        if isinstance(skill_config, dict):
            configured = skill_config.get("react_timeout_seconds") or skill_config.get("timeout_seconds")
    try:
        value = float(configured) if configured is not None else DEFAULT_INVOCATION_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        value = DEFAULT_INVOCATION_TIMEOUT_SECONDS
    return max(10.0, min(value, float(LLMSettings.AGENT_TIMEOUT)))


def _replan_signal_key(signal: dict[str, Any]) -> str:
    return "|".join(
        [
            str(signal.get("source_invocation_id") or ""),
            str(signal.get("trigger") or ""),
            ",".join(str(code) for code in signal.get("failure_codes") or []),
            str(signal.get("recommended_action") or ""),
        ]
    )


def _prepend_current_harness_evidence(
    entries: list[dict[str, Any]],
    current: list[Any],
) -> list[dict[str, Any]]:
    seen = {
        str(entry.get("node_id") or "")
        for entry in entries
        if str(entry.get("node_id") or "").strip()
    }
    retained: list[dict[str, Any]] = []
    for item in current:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id") or "").strip()
        if node_id and node_id in seen:
            continue
        retained.append(item)
    return [*entries, *retained][:8]


def _merge_non_empty_harness(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if value in (None, {}, []):
            continue
        target[key] = value


def _has_replayable_harness_evidence(harness: dict[str, Any]) -> bool:
    return any(
        harness.get(key) not in (None, {}, [])
        for key in (
            "file_change_summary",
            "tool_failure_summary",
            "sandbox_execution_summary",
            "output_ref_summary",
            "reproducibility_summary",
            "experiment_interpretation_summary",
            "statistical_robustness_summary",
            "member_execution_transcript",
            "replan_signals",
            "run_journal_summary",
        )
    )


def _workspace_type_from_brief_or_capability(brief: TaskBrief, capability: Any) -> str:
    raw_brief = brief.brief if isinstance(brief.brief, dict) else {}
    for value in (
        raw_brief.get("workspace_type"),
        raw_brief.get("workspace_kind"),
        getattr(capability, "workspace_type", None),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "unknown"


def _matching_core_template_ids(
    task: dict[str, Any],
    templates: dict[str, AgentTemplate],
    core_template_ids: set[str],
) -> list[str]:
    task_name = _normalized_task_key(task.get("name"))
    skill_id = str(task.get("skill_id") or "").strip()
    matches: list[str] = []
    for template_id in core_template_ids:
        template = templates.get(template_id)
        if template is None:
            continue
        template_name = _normalized_task_key(template_id.split(".")[0])
        if task_name and task_name == template_name:
            matches.append(template_id)
            continue
        if skill_id and skill_id in template.default_skills:
            matches.append(template_id)
    return matches


def _normalized_task_key(value: Any) -> str:
    text = str(value or "").strip().replace("-", "_")
    return text.lower()


def _bounded_paper_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _bounded_paper_value(item.get(key))
        for key in ("title", "authors", "year", "venue", "doi", "url", "source", "abstract")
        if item.get(key) not in (None, "", [])
    }


def _bounded_paper_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:800]
    if isinstance(value, list):
        return [str(item)[:120] for item in value[:8]]
    return value


def _safe_review_item_id(value: Any) -> str:
    text = str(value or "").strip()
    chars: list[str] = []
    last_was_dash = False
    for char in text:
        if char.isalnum() or char in {"_", ".", "-"}:
            chars.append(char)
            last_was_dash = False
            continue
        if not last_was_dash:
            chars.append("-")
            last_was_dash = True
    result = "".join(chars).strip("-._")
    return result[:80] or "research-evidence"


def _has_meaningful_output(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, dict):
        return any(_has_meaningful_output(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_meaningful_output(item) for item in value)
    return bool(value)
