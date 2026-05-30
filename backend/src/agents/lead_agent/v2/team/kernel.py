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
            invocations = await self._run_iteration(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
            )
            gates = self._run_quality_gates(team_policy.quality_pipeline, invocations)
            for gate in gates:
                await self.publish_event(
                    execution_id,
                    "execution.team.quality_gate",
                    {"quality_gate": gate.model_dump(mode="json")},
                )
            duration = int((datetime.now(UTC) - started_at).total_seconds())
            outputs: list[ResultOutput] = list(self._outputs_from_invocations(invocations))
            outputs.extend(self.collect_policy_memory_outputs(capability, brief, outputs))
            return TaskReport(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                status="completed",
                duration_seconds=duration,
                token_usage=self._aggregate_token_usage(invocations),
                narrative=self._build_narrative(capability, invocations, gates),
                outputs=outputs,
                errors=[],
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
    ) -> list[AgentInvocation]:
        selected_template_ids = team_policy.core_templates[: team_policy.limits.max_parallel_invocations]
        counts: Counter[str] = Counter()
        invocations: list[AgentInvocation] = []
        for template_id in selected_template_ids:
            template = templates[template_id]
            counts[template_id] += 1
            effective_tools = resolve_effective_tools(template, team_policy)
            effective_skills = resolve_effective_skills(
                template,
                capability_skills=team_policy.capability_skills or template.default_skills,
            )
            invocation = build_invocation_assignment(
                template=template,
                iteration=1,
                template_invocation_count=counts[template_id],
                reason="core team member for capability",
                input_brief=self._build_member_brief(brief, capability, template, blackboard),
                effective_tools=effective_tools,
                effective_skills=effective_skills,
            )
            invocation.execution_id = execution_id
            invocations.append(invocation)

        await asyncio.gather(
            *[
                self._run_invocation(
                    invocation=invocation,
                    template=templates[invocation.template_id],
                    capability_policy=capability_policy,
                    workspace_data=workspace_data,
                    blackboard=blackboard,
                )
                for invocation in invocations
            ]
        )
        return invocations

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
                return
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

    def _run_quality_gates(
        self,
        quality_pipeline: list[str],
        invocations: list[AgentInvocation],
    ) -> list[QualityGateResult]:
        failed = [item for item in invocations if item.status == "failed"]
        status = "warning" if failed else "pass"
        gates = quality_pipeline or ["team_output_available"]
        return [
            QualityGateResult(
                gate_id=gate,
                status=status,
                severity="medium" if failed else "low",
                findings=[{"message": f"{len(failed)} team member invocation(s) failed"}] if failed else [],
                next_action="stop_with_warning" if failed else "finish",
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

    @staticmethod
    def _preview_output(output: Any) -> str:
        if isinstance(output, dict):
            for key in ("summary", "report_markdown", "markdown", "text"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return json.dumps(output, ensure_ascii=False, sort_keys=True)
        return str(output or "")
