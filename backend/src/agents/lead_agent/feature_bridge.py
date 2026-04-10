"""Deterministic bridge for workspace feature orchestration from chat."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from src.academic.cache.redis_client import redis_client
from src.academic.services.workspace_service import WorkspaceService
from src.agents.lead_agent.feature_bridge_cards import (
    build_chat_result_card,
    build_confirmation_required_response,
    build_feature_task_completion_card,
    build_feature_task_failure_card,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_execution_success_response as _build_execution_success_response,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_execution_warning_response as _build_execution_warning_response,
)
from src.agents.lead_agent.feature_bridge_catalog import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
)
from src.agents.lead_agent.feature_bridge_models import BridgedChatResponse
from src.application.handlers.feature_execution_handler import FeatureExecutionHandler
from src.config import redis_settings
from src.database import Workspace, get_db_session
from src.services.credit_service import CreditService
from src.services.literature_service import LiteratureService
from src.task.service import TaskService
from src.task.store import TaskStore
from src.task.workspace_feature_params import coerce_workspace_feature_params

__all__ = [
    "BridgedChatResponse",
    "build_chat_result_card",
    "build_confirmation_required_response",
    "build_feature_task_completion_card",
    "build_feature_task_failure_card",
    "build_workspace_artifact_overview",
    "build_workspace_feature_overview",
    "execute_workspace_feature_request",
    "_coerce_task_params",
    "_execute_workspace_feature_request",
]

logger = logging.getLogger(__name__)


async def _execute_workspace_feature_request(
    *,
    db: Any,
    workspace: Workspace,
    workspace_service: WorkspaceService,
    feature_id: str,
    params: Mapping[str, Any] | None,
    thread_id: str | None,
    user_id: str,
    skill_id: str | None = None,
) -> BridgedChatResponse:
    resolved_params = dict(params or {})
    task_service = TaskService(TaskStore(redis_client, db))
    literature_service = LiteratureService(db)
    credit_service = CreditService(db)
    handler = FeatureExecutionHandler(
        actor_id=str(user_id),
        workspace_service=workspace_service,
        task_service=task_service,
        literature_service=literature_service,
        credit_service=credit_service,
    )

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )
    execution = await handler.execute(
        str(workspace.id),
        feature_id,
        resolved_params,
        thread_id,
        skill_id,
        redis_client=runtime_redis,
    )

    if getattr(execution, "task_id", None):
        return _build_execution_success_response(
            feature_id=feature_id,
            task_id=str(execution.task_id),
            message=str(execution.message),
            params=resolved_params,
        )

    return _build_execution_warning_response(
        feature_id=feature_id,
        execution=execution,
        params=resolved_params,
    )


async def execute_workspace_feature_request(
    *,
    workspace_id: str | None,
    thread_id: str | None,
    user_id: str,
    feature_id: str,
    params: Mapping[str, Any] | None = None,
    skill_id: str | None = None,
) -> BridgedChatResponse | None:
    """Execute a resolved workspace feature through the canonical application handler."""
    if not workspace_id:
        return None

    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get(workspace_id)
        if workspace is None:
            return None
        if str(workspace.user_id) != str(user_id):
            logger.warning(
                "Skipping feature execution for unowned workspace %s and user %s",
                workspace_id,
                user_id,
            )
            return None

        return await _execute_workspace_feature_request(
            db=db,
            workspace=workspace,
            workspace_service=workspace_service,
            feature_id=feature_id,
            params=params,
            thread_id=thread_id,
            user_id=user_id,
            skill_id=skill_id,
        )

def _coerce_task_params(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return coerce_workspace_feature_params(payload)
