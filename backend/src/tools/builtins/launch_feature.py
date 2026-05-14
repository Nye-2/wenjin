"""launch_feature builtin tool — dispatches a capability via the v2 execution pipeline."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError


class LaunchFeatureInput(BaseModel):
    feature_id: str = Field(
        ...,
        description="Capability id, e.g. 'paper_analysis', 'deep_research', 'writing'.",
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


@tool("launch_feature", args_schema=LaunchFeatureInput)
async def launch_feature_tool(
    feature_id: str,
    params: dict[str, Any],
    skill_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Launch a workspace capability by id with the given params.

    Creates an ExecutionRecord and dispatches the v2 execution engine.
    Returns a dict with `status` ('dispatched'), `execution_id`, and `feature_id`.
    """
    workspace_id = _read_required(config, "workspace_id")
    thread_id = _read_required(config, "thread_id")
    user_id = _read_required(config, "user_id")

    from src.database import get_db_session
    from src.database.models.capability import Capability
    from src.services.execution_service import ExecutionService
    from src.services.workspace_skill_labels import get_workspace_type
    from sqlalchemy import select

    async with get_db_session() as db:
        # Validate the capability exists for this workspace's type.
        workspace_type = await get_workspace_type(db, workspace_id) or "thesis"
        cap_query = await db.execute(
            select(Capability).where(
                Capability.id == feature_id,
                Capability.workspace_type == workspace_type,
                Capability.enabled.is_(True),
            )
        )
        cap = cap_query.scalar_one_or_none()
        if cap is None:
            # Return the available list so the model can retry with a valid id.
            avail_query = await db.execute(
                select(Capability.id).where(
                    Capability.workspace_type == workspace_type,
                    Capability.enabled.is_(True),
                )
            )
            available_ids = [row[0] for row in avail_query.all()]
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

        execution_service = ExecutionService(db)

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
                "detail": f"正在执行「{feature_label}」({progress}%)，请稍候。",
            }

        from src.config.app_config import celery_settings

        if not celery_settings.enabled:
            return {
                "status": "error",
                "code": "execution_backend_unavailable",
                "feature_id": feature_id,
                "detail": "后台执行服务未启用，请联系管理员。",
            }

        try:
            execution = await execution_service.create_execution(
                workspace_id=workspace_id,
                thread_id=thread_id,
                user_id=user_id,
                execution_type="capability",
                feature_id=feature_id,
                display_name=getattr(cap, "display_name", None),
                workspace_type=workspace_type,
                params={
                    "brief": {
                        "capability_id": feature_id,
                        "brief": dict(params or {}),
                        "raw_message": str(params.get("query") or params.get("topic") or feature_id),
                        "decisions": {},
                        "workspace_id": workspace_id,
                    },
                },
                commit=False,
            )
        except IntegrityError:
            await db.rollback()
            return {
                "status": "advisory",
                "code": "lead_busy",
                "feature_id": feature_id,
                "detail": "已有执行正在运行，请稍候。",
            }

    # Dispatch Celery task to run the execution
    from src.task.tasks.execution import execute_execution

    try:
        execute_execution.apply_async(
            args=[str(execution.id)],
            queue="long_running",
        )
    except Exception:
        from src.database import get_db_session
        from src.services.execution_service import ExecutionService

        async with get_db_session() as db:
            svc = ExecutionService(db)
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

    return {
        "status": "launched",
        "execution_id": str(execution.id),
        "feature_id": feature_id,
        "message": f"已启动「{feature_id}」",
    }
