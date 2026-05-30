"""launch_feature builtin tool — dispatches a capability via the v2 execution pipeline."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.application.services.feature_launch_context import (
    build_execution_launch_params,
    build_missing_context_advisory,
    resolve_missing_context_fields,
)
from src.dataservice_client.errors import DataServiceClientError


class LaunchFeatureInput(BaseModel):
    feature_id: str = Field(
        ...,
        description="Mission capability id, e.g. 'idea_to_thesis_manuscript' or 'research_question_to_paper'.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Capability-specific parameters (paper_title, topic, query, etc.).",
    )
    skill_id: str | None = Field(
        default=None,
        description="Optional skill id when the user has selected one.",
    )


def _read_required(config: RunnableConfig | None, key: str) -> str:
    configurable = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        raise ValueError(f"launch_feature requires '{key}' in runnable config")
    value = str(configurable.get(key) or "").strip()
    if not value:
        raise ValueError(f"launch_feature requires non-empty '{key}'")
    return value


def _read_optional(config: RunnableConfig | None, key: str) -> str | None:
    configurable = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        return None
    value = str(configurable.get(key) or "").strip()
    return value or None


def _read_optional_mapping(config: RunnableConfig | None, key: str) -> dict[str, Any]:
    configurable = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        return {}
    value = configurable.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(param_key): param_value for param_key, param_value in value.items() if isinstance(param_key, str)}


@tool("launch_feature", args_schema=LaunchFeatureInput)
async def launch_feature_tool(
    feature_id: str,
    params: dict[str, Any],
    skill_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Launch a workspace capability by id with the given params.

    Creates an ExecutionRecord and dispatches the v2 execution engine.
    Returns a dict with `status`, `execution_id`, and `feature_id`.
    """
    workspace_id = _read_required(config, "workspace_id")
    thread_id = _read_required(config, "thread_id")
    user_id = _read_required(config, "user_id")
    entry_skill_id = (skill_id or _read_optional(config, "selected_skill") or None)
    execution_id = _read_optional(config, "execution_id")
    runtime_launch_params = _read_optional_mapping(config, "launch_feature_params")
    merged_params = dict(runtime_launch_params)
    merged_params.update(params or {})

    from src.dataservice_client.provider import dataservice_client
    from src.services.execution_service import ExecutionService

    async with dataservice_client() as catalog:
        workspace = await catalog.get_workspace(workspace_id)
        if workspace is None:
            return {
                "status": "error",
                "code": "unknown_workspace",
                "feature_id": feature_id,
                "detail": "当前工作区不存在，无法启动功能任务。",
            }
        workspace_type = workspace.workspace_type
        cap = await catalog.get_catalog_capability(
            capability_id=feature_id,
            workspace_type=workspace_type,
            enabled_only=True,
        )
        available = (
            []
            if cap is not None
            else await catalog.list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=True,
            )
        )
        if cap is None:
            # Return the available list so the model can retry with a valid id.
            available_ids = [item.id for item in available]
            return {
                "status": "error",
                "code": "unknown_feature",
                "feature_id": feature_id,
                "detail": (
                    f"Feature '{feature_id}' is not available for workspace_type "
                    f"'{workspace_type}'. Available feature_ids: {available_ids}. "
                    f"Pick one of these and call launch_feature again."
                ),
            }
        if getattr(cap, "schema_version", None) != "capability.v2":
            return {
                "status": "error",
                "code": "unsupported_capability_schema",
                "feature_id": feature_id,
                "detail": (
                    f"Capability '{feature_id}' uses unsupported schema "
                    f"'{getattr(cap, 'schema_version', None)}'. Runtime requires capability.v2."
                ),
            }

        execution_service = ExecutionService(dataservice=catalog)

        # Lead-busy check
        all_active = await execution_service.list_executions(
            workspace_id=workspace_id,
            status=["pending", "running", "cancelling"],
        )
        if all_active:
            active = all_active[0]
            feature_label = getattr(active, "feature_id", "unknown")
            progress = getattr(active, "progress", 0)
            return {
                "status": "advisory",
                "code": "lead_busy",
                "feature_id": feature_id,
                "execution_id": getattr(active, "id", None),
                "detail": f"正在执行「{feature_label}」({progress}%)，请稍候。",
            }

        from src.services.credit_service import CreditService

        credit_service = CreditService()
        if not await credit_service.can_start_feature_task(user_id):
            policy = credit_service.get_feature_billing_policy()
            return {
                "status": "advisory",
                "code": "feature_credits_required",
                "feature_id": feature_id,
                "detail": (
                    f"功能任务积分不足。当前策略为前 {policy.free_tokens} tokens 免费，"
                    f"之后每 {policy.tokens_per_credit} tokens 扣 1 积分，请先补充积分。"
                ),
            }

        from src.config.app_config import celery_settings

        if not celery_settings.enabled:
            return {
                "status": "error",
                "code": "execution_backend_unavailable",
                "feature_id": feature_id,
                "detail": "后台执行服务未启用，请联系管理员。",
            }

        missing_fields = resolve_missing_context_fields(
            feature_id=feature_id,
            params=merged_params,
            launch_source="tool",
        )
        if missing_fields:
            advisory = build_missing_context_advisory(
                feature_id=feature_id,
                missing_fields=missing_fields,
            )
            return {
                "status": "advisory",
                "code": advisory.code,
                "feature_id": feature_id,
                "detail": advisory.message,
                "context": advisory.context or {},
            }

        execution_params = build_execution_launch_params(
            feature_id=feature_id,
            params=merged_params,
            workspace_id=workspace_id,
        )

        try:
            execution = None
            if execution_id:
                existing_execution = await execution_service.get_by_id(execution_id)
                existing_feature_id = (
                    str(existing_execution.feature_id or "").strip()
                    if existing_execution is not None
                    else ""
                )
                owns_execution = (
                    existing_execution is not None
                    and str(getattr(existing_execution, "workspace_id", "") or "") == workspace_id
                    and str(getattr(existing_execution, "user_id", "") or "") == user_id
                )
                feature_matches = (
                    existing_execution is not None
                    and (not existing_feature_id or existing_feature_id == feature_id)
                )
                if not owns_execution or not feature_matches:
                    return {
                        "status": "error",
                        "code": "unknown_execution",
                        "feature_id": feature_id,
                        "execution_id": execution_id,
                        "detail": "请求恢复的执行不存在，或不属于当前工作区。",
                    }
                execution = await execution_service.update_execution(
                    execution_id,
                    status="pending",
                    thread_id=thread_id,
                    entry_skill_id=entry_skill_id,
                    workspace_type=workspace_type,
                    display_name=getattr(cap, "display_name", None),
                    params=execution_params,
                    result=None,
                    error=None,
                    result_summary=None,
                    graph_structure=None,
                    runtime_state=None,
                    progress=0,
                    message=None,
                    artifact_ids=[],
                    next_actions=[],
                    advisory_code=None,
                    last_error=None,
                    dispatch_mode=None,
                    worker_task_id=None,
                    started_at=None,
                    completed_at=None,
                    commit=False,
                )

            if execution is None:
                execution = await execution_service.create_execution(
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    execution_type="feature",
                    feature_id=feature_id,
                    entry_skill_id=entry_skill_id,
                    display_name=getattr(cap, "display_name", None),
                    workspace_type=workspace_type,
                    params=execution_params,
                    commit=False,
                )
        except DataServiceClientError as exc:
            if exc.status_code != 409:
                raise
            return {
                "status": "advisory",
                "code": "lead_busy",
                "feature_id": feature_id,
                "execution_id": None,
                "detail": "已有执行正在运行，请稍候。",
            }

    # Dispatch through the project Celery app rather than the shared_task proxy.
    # The chat gateway process does not own worker task registration, so using
    # send_task keeps dispatch bound to Wenjin's configured broker/app.
    from src.task.celery_app import celery_app

    worker_task_id: str | None = None
    try:
        worker_task = celery_app.send_task(
            "src.task.tasks.execute_execution",
            args=[str(execution.id)],
            queue="long_running",
        )
        worker_task_id = str(getattr(worker_task, "id", "") or "") or None
    except Exception:
        from src.services.execution_service import ExecutionService

        async with dataservice_client() as catalog:
            svc = ExecutionService(dataservice=catalog)
            await svc.complete_execution(
                str(execution.id),
                status="failed",
                error="Failed to dispatch execution to worker queue",
                result_summary="后台执行队列暂时不可用，请稍后重试。",
            )
        return {
            "status": "error",
            "code": "execution_queue_unavailable",
            "feature_id": feature_id,
            "detail": "后台执行队列暂时不可用，请稍后重试。",
        }

    if worker_task_id:
        try:
            from src.services.execution_service import ExecutionService

            async with dataservice_client() as catalog:
                svc = ExecutionService(dataservice=catalog)
                await svc.update_execution(
                    str(execution.id),
                    dispatch_mode="celery_worker",
                    worker_task_id=worker_task_id,
                )
        except Exception:
            # Dispatch already succeeded. Missing dispatch metadata should not
            # convert a valid execution into a failed launch.
            pass

    return {
        "status": "launched",
        "execution_id": str(execution.id),
        "feature_id": feature_id,
        "capability_name": getattr(cap, "display_name", None),
        "message": f"已启动「{getattr(cap, 'display_name', None) or feature_id}」",
    }
