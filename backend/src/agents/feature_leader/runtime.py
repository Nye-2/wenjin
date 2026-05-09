"""Dedicated feature-domain leader runtime.

This runtime isolates feature execution orchestration from thread mainline
responsibilities. Task handlers call this facade instead of directly coupling
to thread lead-agent code.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.harness import (
    AgentHarness,
    AgentSessionRequest,
    NativeWenjinAgentHarness,
)
from src.agents.harness.contracts import PhaseResult  # type: ignore[attr-defined]
from src.task.runtime_blocks import (
    append_runtime_activity,
    get_runtime_state,
    upsert_runtime_block,
)
from src.task.runtime_blocks import (
    emit_bound_runtime as _emit_bound_runtime,
)
from src.workspace_features.runtime_profiles import (
    FeatureRuntimeProfile,
    get_feature_runtime_profile,
)

from .workflow import (
    build_dynamic_feature_workflow_plan,
    validate_workflow_plan_against_profile,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _preview_payload(value: Any, *, max_chars: int = 220) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        normalized = _normalize_text(value)
    else:
        try:
            normalized = _normalize_text(json.dumps(value, ensure_ascii=False))
        except TypeError:
            normalized = _normalize_text(str(value))
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


class FeatureLeaderRuntime:
    """Facade around workspace feature graph execution."""

    @staticmethod
    def _build_workflow_context(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        params = payload.get("params")
        params = params if isinstance(params, dict) else {}
        execution_session_id = _normalize_text(
            payload.get("execution_session_id")
        )
        context: dict[str, Any] = {
            "workspace_id": _normalize_text(payload.get("workspace_id")),
            "thread_id": _normalize_text(payload.get("thread_id")),
            "user_id": _normalize_text(payload.get("user_id") or payload.get("created_by")),
            "execution_session_id": execution_session_id,
            "execution_id": _normalize_text(payload.get("execution_id")),
            "model_name": _normalize_text(params.get("model_id") or payload.get("model_id")),
            "trace_id": _normalize_text(
                payload.get("trace_id") or execution_session_id or payload.get("task_id")
            ),
        }
        return {key: value for key, value in context.items() if value}

    @staticmethod
    def _serialize_runtime_profile(profile: FeatureRuntimeProfile) -> dict[str, Any]:
        return {
            "workspace_type": profile.workspace_type,
            "feature_id": profile.feature_id,
            "runtime_mode": str(profile.runtime_mode),
            "requires_compute": profile.requires_compute,
            "requires_sandbox": profile.requires_sandbox,
            "allowed_subagents": list(profile.allowed_subagents),
            "max_subagents": profile.max_subagents,
            "agent_harness_provider": profile.agent_harness_provider,
            "output_contract": profile.output_contract,
            "review_gate": profile.review_gate,
        }

    def _build_agent_harness(
        self,
        payload: dict[str, Any],
        profile: FeatureRuntimeProfile,
    ) -> AgentHarness:
        _ = payload
        provider = _normalize_text(
            profile.agent_harness_provider or "native_wenjin"
        ).lower()
        if provider in {"native", "native_wenjin"}:
            return NativeWenjinAgentHarness(
                max_concurrent=profile.max_subagents or None,
            )
        raise ValueError(
            "unsupported_agent_harness_provider: "
            f"{profile.workspace_type}.{profile.feature_id} provider={provider}"
        )

    @staticmethod
    def _serialize_phase_result(result: PhaseResult) -> dict[str, Any]:
        serialized_tasks: list[dict[str, Any]] = []
        for task in result.task_results:
            if not isinstance(task, dict):
                serialized_tasks.append(
                    {
                        "success": False,
                        "error": "invalid_task_result",
                    }
                )
                continue
            serialized_tasks.append(
                {
                    "subagent_type": _normalize_text(task.get("subagent_type")) or None,
                    "success": bool(task.get("success")),
                    "error": _normalize_text(task.get("error")) or None,
                    "result_preview": _preview_payload(task.get("result")) or None,
                    "token_usage": (
                        task.get("token_usage")
                        if isinstance(task.get("token_usage"), dict)
                        else None
                    ),
                }
            )
        return {
            "phase": result.phase_name,
            "success": result.success,
            "error": _normalize_text(result.error) or None,
            "tasks": serialized_tasks,
        }

    @staticmethod
    def _build_workflow_phase_items(
        serialized_phases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for phase in serialized_phases[:10]:
            if not isinstance(phase, dict):
                continue
            tasks = phase.get("tasks")
            task_list = tasks if isinstance(tasks, list) else []
            total = len(task_list)
            success_count = sum(
                1
                for task in task_list
                if isinstance(task, dict) and bool(task.get("success"))
            )
            description = _normalize_text(phase.get("error")) or f"{success_count}/{total} 子任务成功"
            items.append(
                {
                    "title": str(phase.get("phase") or "workflow_phase"),
                    "description": description,
                    "meta": "成功" if bool(phase.get("success")) else "失败",
                    "badge": str(total),
                }
            )
        return items

    async def _publish_workflow_runtime(
        self,
        *,
        strategy: str,
        status: str,
        phase_count: int,
        task_count: int,
        serialized_phases: list[dict[str, Any]],
        activity_title: str,
        activity_description: str,
        activity_tone: str,
        progress_message: str,
    ) -> None:
        runtime = get_runtime_state()
        if runtime is None:
            return

        upsert_runtime_block(
            runtime,
            {
                "id": "leader-workflow",
                "kind": "metrics",
                "title": "Leader 编排",
                "entries": [
                    {"label": "策略", "value": strategy},
                    {"label": "状态", "value": status},
                    {"label": "阶段", "value": str(phase_count)},
                    {"label": "子任务", "value": str(task_count)},
                ],
            },
        )
        phase_items = self._build_workflow_phase_items(serialized_phases)
        if phase_items:
            upsert_runtime_block(
                runtime,
                {
                    "id": "leader-workflow-phases",
                    "kind": "list",
                    "title": "Workflow 阶段",
                    "description": "feature leader 的子代理编排执行结果",
                    "items": phase_items,
                },
            )
        append_runtime_activity(
            runtime,
            title=activity_title,
            description=activity_description,
            tone=activity_tone,
        )
        current_phase = _normalize_text(runtime.get("current_phase"))
        if current_phase:
            await _emit_bound_runtime(
                message=progress_message,
                current_phase=current_phase,
                stage_transition=False,
            )

    async def _run_dynamic_workflow(
        self,
        *,
        workspace_type: str,
        feature_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        profile = get_feature_runtime_profile(workspace_type, feature_id)
        plan = build_dynamic_feature_workflow_plan(
            workspace_type=workspace_type,
            feature_id=feature_id,
            payload=payload,
        )
        if plan is None:
            return None
        if profile is None:
            raise RuntimeError(
                f"feature_runtime_profile_missing: {workspace_type}.{feature_id}"
            )
        validate_workflow_plan_against_profile(plan, profile)

        context = self._build_workflow_context(payload)
        if not context.get("execution_session_id"):
            raise RuntimeError(
                "feature_leader_workflow_missing_execution_session_id: "
                f"{workspace_type}.{feature_id}"
            )

        profile_metadata = self._serialize_runtime_profile(profile)
        agent_harness = self._build_agent_harness(payload, profile)
        partial_phases: list[dict[str, Any]] = []
        await self._publish_workflow_runtime(
            strategy=plan.strategy,
            status="running",
            phase_count=plan.phase_count,
            task_count=plan.task_count,
            serialized_phases=[],
            activity_title="Leader 编排启动",
            activity_description="已进入子代理动态编排阶段。",
            activity_tone="info",
            progress_message="Feature Leader 正在执行子代理编排...",
        )

        async def _phase_callback(phase_result: PhaseResult) -> None:
            serialized = self._serialize_phase_result(phase_result)
            partial_phases.append(serialized)
            await self._publish_workflow_runtime(
                strategy=plan.strategy,
                status="running",
                phase_count=plan.phase_count,
                task_count=plan.task_count,
                serialized_phases=list(partial_phases),
                activity_title=f"Workflow 阶段完成：{serialized.get('phase')}",
                activity_description=(
                    "阶段成功推进。"
                    if bool(serialized.get("success"))
                    else f"阶段失败：{serialized.get('error') or 'unknown_error'}"
                ),
                activity_tone="success" if bool(serialized.get("success")) else "warning",
                progress_message=f"Feature Leader 阶段 {serialized.get('phase')} 已完成",
            )

        try:
            execution_context = {
                **context,
                "workflow_strategy": plan.strategy,
                "runtime_profile": profile_metadata,
            }
            session_result = await agent_harness.run_session(
                AgentSessionRequest(
                    strategy=plan.strategy,
                    phased_plan=plan.phased_plan,
                    context=execution_context,
                    phase_callback=_phase_callback,
                )
            )
            phase_results = session_result.phase_results
        except Exception as exc:
            logger.warning(
                "Feature leader workflow execution failed for %s.%s",
                workspace_type,
                feature_id,
                exc_info=True,
            )
            await self._publish_workflow_runtime(
                strategy=plan.strategy,
                status="failed",
                phase_count=plan.phase_count,
                task_count=plan.task_count,
                serialized_phases=list(partial_phases),
                activity_title="Leader 编排失败",
                activity_description=_normalize_text(exc) or exc.__class__.__name__,
                activity_tone="danger",
                progress_message="Feature Leader 编排失败。",
            )
            raise RuntimeError(
                f"feature_leader_workflow_failed: {workspace_type}.{feature_id}: "
                f"{_normalize_text(exc) or exc.__class__.__name__}"
            ) from exc
        provider = session_result.provider

        serialized_phases = [
            self._serialize_phase_result(result)
            for result in phase_results
        ]
        success = all(bool(phase.get("success")) for phase in serialized_phases)
        if not success:
            await self._publish_workflow_runtime(
                strategy=plan.strategy,
                status="failed",
                phase_count=plan.phase_count,
                task_count=plan.task_count,
                serialized_phases=serialized_phases,
                activity_title="Leader 编排失败",
                activity_description="至少一个 workflow 阶段失败。",
                activity_tone="danger",
                progress_message="Feature Leader 阶段失败，任务终止。",
            )
            raise RuntimeError(
                f"feature_leader_workflow_phase_failed: {workspace_type}.{feature_id}"
            )

        await self._publish_workflow_runtime(
            strategy=plan.strategy,
            status="completed",
            phase_count=plan.phase_count,
            task_count=plan.task_count,
            serialized_phases=serialized_phases,
            activity_title="Leader 编排结束",
            activity_description="所有 workflow 阶段已结束。",
            activity_tone="success",
            progress_message="Feature Leader 子代理编排已完成。",
        )
        return {
            "enabled": True,
            "status": "completed",
            "provider": provider,
            "strategy": plan.strategy,
            "runtime_profile": profile_metadata,
            "phase_count": plan.phase_count,
            "task_count": plan.task_count,
            "phases": serialized_phases,
        }

    @staticmethod
    def _inject_workflow_context(
        payload: dict[str, Any],
        workflow: dict[str, Any],
    ) -> dict[str, Any]:
        updated_payload = dict(payload)
        params = updated_payload.get("params")
        base_params = dict(params) if isinstance(params, dict) else {}
        base_params["__leader_workflow"] = {
            "status": workflow.get("status"),
            "provider": workflow.get("provider"),
            "strategy": workflow.get("strategy"),
            "phase_count": workflow.get("phase_count"),
            "task_count": workflow.get("task_count"),
        }

        highlights: list[str] = []
        for phase in workflow.get("phases") or []:
            if not isinstance(phase, dict):
                continue
            for task in phase.get("tasks") or []:
                if not isinstance(task, dict):
                    continue
                preview = _normalize_text(task.get("result_preview"))
                if preview:
                    highlights.append(preview)
                if len(highlights) >= 3:
                    break
            if len(highlights) >= 3:
                break
        if highlights:
            base_params["__leader_workflow_highlights"] = "；".join(highlights)

        updated_payload["params"] = base_params
        return updated_payload

    async def execute_feature(
        self,
        *,
        workspace_type: str,
        feature_id: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from src.agents.feature_leader.graph_registry import execute_feature_graph

        workflow = await self._run_dynamic_workflow(
            workspace_type=workspace_type,
            feature_id=feature_id,
            payload=payload,
        )
        effective_payload = (
            self._inject_workflow_context(payload, workflow)
            if isinstance(workflow, dict)
            else payload
        )

        result = await execute_feature_graph(
            workspace_type,
            feature_id,
            effective_payload,
            user_id=user_id,
        )
        if not isinstance(result, dict):
            return result
        if workflow is not None:
            return {**result, "leader_workflow": workflow}
        return result


_DEFAULT_RUNTIME = FeatureLeaderRuntime()


def get_feature_leader_runtime() -> FeatureLeaderRuntime:
    """Return the process-wide feature leader runtime facade."""
    return _DEFAULT_RUNTIME
