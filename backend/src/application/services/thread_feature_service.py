"""Application-level adapter for thread/tool-triggered feature launches."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from src.academic.cache.redis_client import redis_client
from src.academic.services.workspace_service import WorkspaceService
from src.application.commands import FeatureLaunchCommand
from src.application.presenters.thread_feature_cards import (
    build_execution_success_response,
    build_execution_warning_response,
)
from src.application.results import GeneratedThreadReply
from src.config import redis_settings
from src.database import Workspace, get_db_session
from src.services.credit_service import CreditService
from src.services.literature_service import LiteratureService
from src.task.service import TaskService
from src.task.store import TaskStore

from .feature_ingress_factory import build_feature_ingress_service

logger = logging.getLogger(__name__)


async def _execute_thread_feature_request(
    *,
    db: Any,
    workspace: Workspace,
    workspace_service: WorkspaceService,
    feature_id: str | None,
    params: Mapping[str, Any] | None,
    thread_id: str | None,
    user_id: str,
    skill_id: str | None = None,
    launch_message: str | None = None,
    execution_session_id: str | None = None,
) -> GeneratedThreadReply:
    resolved_params = dict(params or {})
    launch_service = build_feature_ingress_service(
        actor_id=str(user_id),
        db=db,
        workspace_service=workspace_service,
        task_service=TaskService(TaskStore(redis_client, db)),
        literature_service=LiteratureService(db),
        credit_service=CreditService(db),
    )

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )
    launch = await launch_service.launch(
        FeatureLaunchCommand(
            workspace_id=str(workspace.id),
            feature_id=feature_id,
            params=resolved_params,
            thread_id=thread_id,
            skill_id=skill_id,
            launch_source="thread",
            launch_message=launch_message,
            redis_client=runtime_redis,
            execution_session_id=execution_session_id,
        )
    )
    execution = launch.outcome
    resolved_feature_id = (
        str(getattr(execution, "feature_id", "") or "").strip()
        or str(feature_id or "").strip()
        or "workspace_feature"
    )

    if getattr(execution, "task_id", None):
        return build_execution_success_response(
            feature_id=resolved_feature_id,
            task_id=str(execution.task_id),
            execution_session_id=launch.execution_session_id,
            message=str(execution.message),
            params=resolved_params,
        )

    return build_execution_warning_response(
        feature_id=resolved_feature_id,
        execution_session_id=launch.execution_session_id,
        execution=execution,
        params=resolved_params,
    )


async def execute_workspace_feature_request(
    *,
    workspace_id: str | None,
    thread_id: str | None,
    user_id: str,
    feature_id: str | None,
    params: Mapping[str, Any] | None = None,
    skill_id: str | None = None,
    launch_message: str | None = None,
    execution_session_id: str | None = None,
) -> GeneratedThreadReply | None:
    """Launch/resume a workspace feature and format thread-facing execution cards."""
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

        return await _execute_thread_feature_request(
            db=db,
            workspace=workspace,
            workspace_service=workspace_service,
            feature_id=feature_id,
            params=params,
            thread_id=thread_id,
            user_id=user_id,
            skill_id=skill_id,
            launch_message=launch_message,
            execution_session_id=execution_session_id,
        )
