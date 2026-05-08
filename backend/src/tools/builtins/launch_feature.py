"""launch_feature builtin tool — lead_agent's only path to start a workspace feature."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.academic.cache.redis_client import redis_client
from src.academic.services.workspace_service import WorkspaceService
from src.application.commands import FeatureLaunchCommand
from src.application.services.feature_ingress_factory import (
    build_feature_ingress_service,
)
from src.config import redis_settings
from src.database import get_db_session
from src.services.credit_service import CreditService
from src.services.references import WorkspaceReferenceService
from src.task.service import TaskService
from src.task.store import TaskStore


class LaunchFeatureInput(BaseModel):
    feature_id: str = Field(
        ...,
        description="Workspace feature id, e.g. 'paper_analysis', 'literature_search', 'writing'.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature-specific parameters (paper_title, topic, query, etc.).",
    )
    skill_id: str | None = Field(
        default=None,
        description="Optional skill id when the user has selected one.",
    )
    execution_session_id: str | None = Field(
        default=None,
        description=(
            "When resuming a previous run, pass the execution_session_id to "
            "continue that run instead of starting a new one. The seed prompt "
            "will say 请继续「...」的执行 in this case; the value comes from "
            "the URL params of the chat page."
        ),
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
    execution_session_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Launch a workspace feature by id with the given params.

    When `execution_session_id` is provided, FeatureLaunchService resumes that
    existing run; otherwise a new run is started.

    Returns a dict with `status` ('launched' | 'advisory'), `task_id` (when launched),
    `execution_session_id`, `feature_id`, and either `message` (success) or
    `code`/`detail` (advisory).
    """
    workspace_id = _read_required(config, "workspace_id")
    thread_id = _read_required(config, "thread_id")
    user_id = _read_required(config, "user_id")

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )

    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        launch_service = build_feature_ingress_service(
            actor_id=user_id,
            db=db,
            workspace_service=workspace_service,
            task_service=TaskService(TaskStore(redis_client, db)),
            reference_service=WorkspaceReferenceService(db),
            credit_service=CreditService(db),
        )
        result = await launch_service.launch(
            FeatureLaunchCommand(
                workspace_id=workspace_id,
                feature_id=feature_id,
                params=dict(params or {}),
                thread_id=thread_id,
                skill_id=skill_id,
                launch_source="thread",
                redis_client=runtime_redis,
                execution_session_id=execution_session_id,
            )
        )

    outcome = result.outcome
    task_id = getattr(outcome, "task_id", None)
    if task_id:
        return {
            "status": "launched",
            "task_id": str(task_id),
            "execution_session_id": result.execution_session_id,
            "feature_id": str(getattr(outcome, "feature_id", feature_id)),
            "message": str(getattr(outcome, "message", "")),
        }

    return {
        "status": "advisory",
        "execution_session_id": result.execution_session_id,
        "feature_id": feature_id,
        "code": str(getattr(outcome, "code", "") or "advisory"),
        "detail": str(getattr(outcome, "message", "") or ""),
    }
