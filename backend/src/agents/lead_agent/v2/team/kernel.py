"""Team-kernel runtime for capability-driven dynamic Lead Agent teams."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
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
from src.dataservice_client.provider import dataservice_client
from src.subagents.v2 import types as _types  # noqa: F401
from src.subagents.v2.base import SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY

from .contracts import AgentInvocation, AgentTemplate, QualityGateResult, TeamBlackboard
from .policy import (
    TeamPolicyError,
    build_capability_team_policy,
    build_invocation_assignment,
    resolve_effective_skills,
    resolve_effective_tools,
)

logger = logging.getLogger(__name__)


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
            outputs: list[ResultOutput] = list(self._outputs_from_invocations(invocations))
            outputs.extend(self.collect_policy_memory_outputs(capability, brief, outputs))
            errors = self._errors_from_invocations(invocations)
            return TaskReport(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                status="failed_partial" if errors else "completed",
                duration_seconds=duration,
                token_usage=self._aggregate_token_usage(invocations),
                narrative=self._build_narrative(capability, invocations, gates),
                outputs=outputs,
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

    async def _load_skills(self, skill_ids: list[str]) -> dict[str, Any]:
        if not skill_ids:
            return {}
        async with dataservice_client() as client:
            records = await client.list_catalog_skills(enabled_only=True)
        wanted = set(skill_ids)
        return {record.id: record for record in records if record.id in wanted}

    async def _run_iteration(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: Any,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
    ) -> tuple[list[AgentInvocation], list[QualityGateResult]]:
        counts: Counter[str] = Counter()
        invocations: list[AgentInvocation] = []
        gates: list[QualityGateResult] = []
        core_queue = [
            {
                "template_id": template_id,
                "reason": "core team member for capability",
            }
            for template_id in team_policy.core_templates
        ]
        latest_batch: list[AgentInvocation] = []
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
                iteration=1,
                recruits=current_core,
            )
            if not latest_batch:
                break
            core_invocations.extend(latest_batch)
            if invocations and all(invocation.status == "cancelled" for invocation in invocations):
                break

        if invocations and all(invocation.status == "cancelled" for invocation in invocations):
            return invocations, gates
        if not invocations:
            return invocations, gates

        batch_gates = await self._evaluate_quality_gates(
            execution_id=execution_id,
            team_policy=team_policy,
            counts=counts,
            invocations=invocations,
            latest_invocations=core_invocations or latest_batch,
            blackboard=blackboard,
        )
        gates.extend(batch_gates)
        next_batch = self._next_recruits_from_gates(
            batch_gates,
            counts,
            len(invocations),
            team_policy,
        )
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
                iteration=iteration,
                recruits=next_batch[: team_policy.limits.max_parallel_invocations],
            )
            if not batch:
                break
            if invocations and all(invocation.status == "cancelled" for invocation in invocations):
                break

            batch_gates = await self._evaluate_quality_gates(
                execution_id=execution_id,
                team_policy=team_policy,
                counts=counts,
                invocations=invocations,
                latest_invocations=batch,
                blackboard=blackboard,
            )
            gates.extend(batch_gates)
            recruits = self._next_recruits_from_gates(
                batch_gates,
                counts,
                len(invocations),
                team_policy,
            )
            if not recruits:
                if any(gate.next_action == "recruit_more" for gate in batch_gates):
                    no_progress_rounds += 1
                    if no_progress_rounds >= team_policy.limits.no_progress_rounds_before_stop:
                        break
                break

            no_progress_rounds = 0
            next_batch = recruits
            iteration += 1

        return invocations, gates

    async def _run_invocation_batch(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: Any,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        iteration: int,
        recruits: list[dict[str, str]],
    ) -> list[AgentInvocation]:
        batch = self._build_invocation_batch(
            execution_id=execution_id,
            brief=brief,
            capability=capability,
            templates=templates,
            team_policy=team_policy,
            blackboard=blackboard,
            counts=counts,
            iteration=iteration,
            recruits=recruits,
        )
        invocations.extend(batch)
        if not batch:
            return batch
        await asyncio.gather(
            *[
                self._run_invocation(
                    invocation=invocation,
                    template=templates[invocation.template_id],
                    capability_policy=capability_policy,
                    workspace_data=workspace_data,
                    blackboard=blackboard,
                )
                for invocation in batch
            ]
        )
        return batch

    async def _evaluate_quality_gates(
        self,
        *,
        execution_id: str,
        team_policy: Any,
        counts: Counter[str],
        invocations: list[AgentInvocation],
        latest_invocations: list[AgentInvocation],
        blackboard: TeamBlackboard,
    ) -> list[QualityGateResult]:
        gates = self._run_quality_gates(
            team_policy.quality_pipeline,
            invocations,
            team_policy=team_policy,
            counts=counts,
            latest_invocations=latest_invocations,
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

    def _build_invocation_batch(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy: Any,
        blackboard: TeamBlackboard,
        counts: Counter[str],
        iteration: int,
        recruits: list[dict[str, str]],
    ) -> list[AgentInvocation]:
        batch: list[AgentInvocation] = []
        for recruit in recruits:
            template_id = recruit["template_id"]
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
                reason=recruit["reason"],
                input_brief=self._build_member_brief(brief, capability, template, blackboard),
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
    ) -> dict[str, Any]:
        payload = dict(brief.brief or {})
        payload.setdefault("raw_message", brief.raw_message)
        payload.setdefault("workspace_id", brief.workspace_id)
        payload.setdefault("capability_id", brief.capability_id)
        if brief.user_id:
            payload.setdefault("user_id", brief.user_id)
        payload["team_role"] = template.display_role
        payload["team_blackboard"] = blackboard.model_dump(mode="json")
        payload["capability_name"] = getattr(capability, "display_name", brief.capability_id)
        return payload

    async def _run_invocation(
        self,
        *,
        invocation: AgentInvocation,
        template: AgentTemplate,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
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
                skill_records = await self._load_skills(invocation.effective_skills)
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
                )
                result: SubagentResult = await subagent_cls().run(ctx)
                invocation.status = "succeeded"
                invocation.output_report = result.output
                invocation.tool_calls = result.tool_calls or []
                invocation.token_usage = result.token_usage
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
            node_metadata={
                "team": True,
                "template_id": invocation.template_id,
                "display_name": invocation.display_name,
                "assigned_role": invocation.assigned_role,
                "recruitment_reason": invocation.recruitment_reason,
                "effective_tools": invocation.effective_tools,
                "effective_skills": invocation.effective_skills,
            },
            started_at=started_at,
            completed_at=completed_at,
        )

    def _can_invoke_template(
        self,
        template_id: str,
        counts: Counter[str],
        total_invocations: int,
        team_policy: Any,
    ) -> bool:
        if total_invocations >= team_policy.limits.max_invocations_total:
            return False
        return counts[template_id] < team_policy.limits.max_invocations_per_template

    def _next_recruits_from_gates(
        self,
        gates: list[QualityGateResult],
        counts: Counter[str],
        total_invocations: int,
        team_policy: Any,
    ) -> list[dict[str, str]]:
        recruits: list[dict[str, str]] = []
        seen: set[str] = set()
        remaining_total = team_policy.limits.max_invocations_total - total_invocations
        if remaining_total <= 0:
            return recruits
        batch_limit = min(team_policy.limits.max_parallel_invocations, remaining_total)
        for gate in gates:
            if gate.next_action != "recruit_more":
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
                    {
                        "template_id": template_id,
                        "reason": f"quality gate requested: {reason}",
                    }
                )
                seen.add(template_id)
                if len(recruits) >= batch_limit:
                    return recruits
        return recruits

    def _suggest_recruits(
        self,
        interrupted: list[AgentInvocation],
        *,
        team_policy: Any | None,
        counts: Counter[str] | None,
        total_invocations: int,
    ) -> list[dict[str, str]]:
        if not interrupted or team_policy is None or counts is None:
            return []

        candidate_pairs: list[tuple[str, str]] = []
        if any(invocation.status == "failed" for invocation in interrupted):
            for trigger_key in ("member_failed", "overloaded_or_missing_specialist"):
                candidate_pairs.extend(
                    self._trigger_template_pairs(
                        team_policy,
                        trigger_key,
                        trigger_key,
                    )
                )
        if any(invocation.status == "cancelled" for invocation in interrupted):
            for trigger_key in ("member_cancelled", "overloaded_or_missing_specialist"):
                candidate_pairs.extend(
                    self._trigger_template_pairs(
                        team_policy,
                        trigger_key,
                        trigger_key,
                    )
                )
        if not candidate_pairs:
            candidate_pairs = [
                (template_id, "optional_fallback")
                for template_id in team_policy.optional_templates
            ]

        recruits: list[dict[str, str]] = []
        seen: set[str] = set()
        for template_id, trigger in candidate_pairs:
            if template_id in seen:
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
            recruits.append(
                {
                    "template_id": template_id,
                    "reason": f"{trigger} after interrupted team member",
                }
            )
            seen.add(template_id)
        return recruits

    def _trigger_template_pairs(
        self,
        team_policy: Any,
        trigger_key: str,
        reason: str,
    ) -> list[tuple[str, str]]:
        raw_templates = team_policy.recruitment_triggers.get(trigger_key) or []
        if isinstance(raw_templates, str):
            raw_templates = [raw_templates]
        return [(str(template_id), reason) for template_id in raw_templates]

    def _is_recruitable_template(self, template_id: str, team_policy: Any) -> bool:
        return template_id in {*team_policy.core_templates, *team_policy.optional_templates}

    def _run_quality_gates(
        self,
        quality_pipeline: list[str],
        invocations: list[AgentInvocation],
        *,
        team_policy: Any | None = None,
        counts: Counter[str] | None = None,
        latest_invocations: list[AgentInvocation] | None = None,
    ) -> list[QualityGateResult]:
        failed = [item for item in invocations if item.status == "failed"]
        cancelled = [item for item in invocations if item.status == "cancelled"]
        interrupted = [*failed, *cancelled]
        latest = latest_invocations or invocations
        latest_interrupted = [
            item for item in latest if item.status in {"failed", "cancelled"}
        ]
        suggested_recruits = self._suggest_recruits(
            latest_interrupted,
            team_policy=team_policy,
            counts=counts,
            total_invocations=len(invocations),
        )
        status = "warning" if interrupted else "pass"
        gates = quality_pipeline or ["team_output_available"]
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
                gate_id=gate,
                status=status,
                severity="medium" if interrupted else "low",
                findings=[{"message": finding_message}] if interrupted else [],
                suggested_recruits=[dict(item) for item in suggested_recruits],
                next_action=next_action,
            )
            for gate in gates
        ]

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
