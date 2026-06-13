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
    TaskReport,
)
from src.agents.harness.diff_tracker import (
    build_harness_node_metadata_from_tool_calls,
    build_harness_replan_signals_from_tool_calls,
)
from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver
from src.agents.lead_agent.v2.prism_review_staging import (
    build_prism_file_change_command,
)
from src.agents.lead_agent.v2.sandbox_artifact_review import (
    collect_sandbox_artifact_candidates,
    sandbox_artifact_payload_for_candidate,
    sandbox_review_item_projection,
    workspace_asset_payload_for_candidate,
)
from src.dataservice_client.contracts.execution import ExecutionUpdatePayload
from src.dataservice_client.provider import dataservice_client
from src.services.prism_review_projection import prism_review_item_projection
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


@dataclass(frozen=True, slots=True)
class RecruitmentCandidate:
    template_id: str
    reason: str


@dataclass(slots=True)
class SkillCatalogCache:
    records: dict[str, Any | None] = field(default_factory=dict)
    loaded: bool = False


class TeamKernelRuntime:
    """Fixed control loop for dynamic Lead Agent team execution."""

    def __init__(
        self,
        *,
        publish_event: Callable[[str, str, dict[str, Any]], Awaitable[None]],
        record_node_event: Callable[..., Awaitable[None]],
        abort_check: Callable[[str], Awaitable[bool]],
        load_workspace_data: Callable[[str], Awaitable[dict[str, Any]]],
        needs_library_context: Callable[[dict[str, Any]], bool],
        capability_policy_builder: Callable[[Any], dict[str, Any]],
        collect_policy_memory_outputs: Callable[[Any, TaskBrief, list[ResultOutput]], list[ResultOutput]],
    ) -> None:
        self.publish_event = publish_event
        self.record_node_event = record_node_event
        self.abort_check = abort_check
        self.load_workspace_data = load_workspace_data
        self.needs_library_context = needs_library_context
        self.capability_policy_builder = capability_policy_builder
        self.collect_policy_memory_outputs = collect_policy_memory_outputs

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
            workspace_data = (
                await self.load_workspace_data(brief.workspace_id)
                if self.needs_library_context(capability_policy)
                else {}
            )
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
            )
            if invocations and all(invocation.status == "cancelled" for invocation in invocations):
                return self._cancelled_report(execution_id, brief, started_at)
            duration = int((datetime.now(UTC) - started_at).total_seconds())
            outputs: list[ResultOutput] = self._mapped_outputs_from_graph_template(
                capability,
                invocations,
            )
            if not outputs:
                outputs = list(self._outputs_from_invocations(invocations))
            outputs.extend(self.collect_policy_memory_outputs(capability, brief, outputs))
            errors = [
                *self._errors_from_invocations(invocations),
                *self._errors_from_quality_gates(gates),
            ]
            status = "failed_partial" if errors else "completed"
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
            return TaskReport(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                status=status,
                duration_seconds=duration,
                token_usage=self._aggregate_token_usage(invocations),
                narrative=self._build_narrative(capability, invocations, gates),
                outputs=outputs,
                review_items=review_items,
                preview_item_id=self._result_preview_item_id(invocations),
                errors=errors,
            )
        except TeamPolicyError as exc:
            return self._failed_report(execution_id, brief, started_at, str(exc))
        except Exception as exc:
            logger.exception("team kernel failed", extra={"execution_id": execution_id})
            return self._failed_report(execution_id, brief, started_at, str(exc))

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

    async def _run_iteration(
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
    ) -> tuple[list[AgentInvocation], list[QualityGateResult]]:
        counts: Counter[str] = Counter()
        invocations: list[AgentInvocation] = []
        gates: list[QualityGateResult] = []
        skill_cache = SkillCatalogCache()
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
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        skill_cache: SkillCatalogCache,
    ) -> list[AgentInvocation]:
        core_queue = [
            RecruitmentCandidate(
                template_id=template_id,
                reason="core team member for capability",
            )
            for template_id in team_policy.core_templates
        ]
        core_invocations: list[AgentInvocation] = []
        while core_queue and len(invocations) < team_policy.limits.max_invocations_total:
            current_core = core_queue[: team_policy.limits.max_parallel_invocations]
            core_queue = core_queue[team_policy.limits.max_parallel_invocations :]
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
                break
            core_invocations.extend(latest_batch)
            self._sync_current_harness_evidence(workspace_data, latest_batch)
            if self._all_cancelled(invocations):
                break
        return core_invocations

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
                    workspace_data=workspace_data,
                    blackboard=blackboard,
                    skill_records=skill_cache.records,
                    skill_load_error=skill_load_error,
                )
                for invocation in batch
            ]
        )
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

    @staticmethod
    def _sync_current_harness_evidence(
        workspace_data: dict[str, Any],
        latest_invocations: list[AgentInvocation],
    ) -> None:
        entries: list[dict[str, Any]] = []
        for invocation in latest_invocations:
            harness_metadata = build_harness_node_metadata_from_tool_calls(invocation.tool_calls)
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
            await self.publish_event(
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
        counts: Counter[str],
        iteration: int,
        recruits: list[RecruitmentCandidate],
    ) -> list[AgentInvocation]:
        batch: list[AgentInvocation] = []
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
                ),
                effective_tools=effective_tools,
                effective_skills=effective_skills,
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
    ) -> dict[str, Any]:
        return build_team_member_context(
            brief=brief,
            capability_name=getattr(capability, "display_name", brief.capability_id),
            template_id=template.id,
            display_role=template.display_role,
            blackboard=blackboard,
            capability_policy=capability_policy,
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
        await self._record_invocation(invocation, status="running", started_at=started_at)
        await self.publish_event(
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
                    publish_event=self.publish_event,
                )
                result: SubagentResult = await subagent_cls().run(ctx)
                invocation.status = "succeeded"
                invocation.output_report = result.output
                invocation.tool_calls = result.tool_calls or []
                invocation.token_usage = result.token_usage
                result_metadata = result.metadata if isinstance(result.metadata, dict) else {}
                invocation.expert_snapshots = sanitize_expert_snapshot_items(
                    list(result_metadata.get("expert_snapshots") or []),
                )
                invocation.expert_preview_items = sanitize_expert_preview_items(
                    list(result_metadata.get("expert_preview_items") or []),
                )
                if not invocation.expert_preview_items:
                    preview_item = build_expert_output_preview_item(
                        invocation,
                        summary=self._preview_output(result.output),
                    )
                    if preview_item:
                        invocation.expert_preview_items = [preview_item]
                blackboard.latest_leader_summary = self._preview_output(result.output)
        except Exception as exc:
            invocation.status = "failed"
            invocation.error = {"message": str(exc)}
        completed_at = datetime.now(UTC)
        await self._record_invocation(invocation, status=invocation.status, completed_at=completed_at)
        await self.publish_event(
            invocation.execution_id or "",
            "execution.team.invocation",
            {"invocation": invocation.model_dump(mode="json")},
        )

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
        node_metadata["harness"] = build_expert_node_metadata(
            invocation,
            status=status,
            existing_harness=(
                node_metadata.get("harness")
                if isinstance(node_metadata.get("harness"), dict)
                else None
            ),
        )

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
            outputs.append(
                DocumentOutput(
                    id=f"team-output-{invocation.id}",
                    kind="document",
                    preview=f"{invocation.display_name}: {content[:80]}",
                    default_checked=True,
                    data=DocumentData(
                        name=f"{invocation.display_name}产出.md",
                        doc_kind="team_member_report",
                        content=content,
                    ),
                )
            )
        return outputs

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
        skill_id = str(task.get("skill_id") or "").strip()
        task_name = str(task.get("name") or "").strip()
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            if skill_id and skill_id in invocation.effective_skills:
                return invocation.output_report or {}
        normalized_task_name = task_name.replace("-", "_")
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            template_name = invocation.template_id.split(".")[0].replace("-", "_")
            if normalized_task_name and normalized_task_name == template_name:
                return invocation.output_report or {}
        if self._task_declares_document_output(task):
            content = self._aggregate_team_content(invocations)
            return {"text": content} if content else None
        return None

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

    def _build_narrative(
        self,
        capability: Any,
        invocations: list[AgentInvocation],
        gates: list[QualityGateResult],
    ) -> str:
        names = "、".join(item.display_name for item in invocations)
        warnings = sum(1 for gate in gates if gate.status != "pass")
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
            return json.dumps(output, ensure_ascii=False, sort_keys=True)
        return str(output or "")


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
