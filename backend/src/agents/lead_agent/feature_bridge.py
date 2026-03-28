"""Deterministic bridge for workspace feature orchestration from chat."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from src.academic.cache.redis_client import redis_client
from src.academic.services.workspace_service import WorkspaceService
from src.agents.lead_agent.chat_skill_catalog import (
    SKILL_TO_FEATURE as _SKILL_TO_FEATURE,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_chat_result_card,
    build_feature_task_completion_card,
    build_feature_task_failure_card,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_execution_success_response as _build_execution_success_response,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_execution_warning_response as _build_execution_warning_response,
)
from src.agents.lead_agent.feature_bridge_cards import (
    build_missing_response as _build_missing_response,
)
from src.agents.lead_agent.feature_bridge_catalog import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
)
from src.agents.lead_agent.feature_bridge_catalog import (
    load_latest_draft_summary as _load_latest_draft_summary,
)
from src.agents.lead_agent.feature_bridge_intents import (
    message_has_action_intent as _message_has_action_intent,
)
from src.agents.lead_agent.feature_bridge_intents import (
    resolve_feature_params as _resolve_feature_params,
)
from src.agents.lead_agent.feature_bridge_intents import (
    select_feature_by_message as _select_feature_by_message_entry,
)
from src.agents.lead_agent.feature_bridge_models import (
    BridgedChatResponse,
    FeatureIntent,
)
from src.application.handlers.feature_execution_handler import (
    FeatureExecutionHandler,
    resolve_workspace_type,
)
from src.config import redis_settings
from src.database import Workspace, get_db_session
from src.services.credit_service import CreditService
from src.services.literature_service import LiteratureService
from src.task.service import TaskService
from src.task.store import TaskStore
from src.task.workspace_feature_params import coerce_workspace_feature_params

__all__ = [
    "BridgedChatResponse",
    "FeatureIntent",
    "build_chat_result_card",
    "build_feature_task_completion_card",
    "build_feature_task_failure_card",
    "build_workspace_artifact_overview",
    "build_workspace_feature_overview",
    "execute_workspace_feature_request",
    "is_workspace_chat_orchestration_enabled",
    "maybe_bridge_workspace_feature",
    "_coerce_task_params",
    "_execute_workspace_feature_request",
    "_resolve_feature_intent",
    "_select_feature_by_message",
    "_select_feature_by_skill",
]

logger = logging.getLogger(__name__)

_CHAT_ROLLOUT_DEFAULT_TYPES = {
    "thesis",
    "sci",
    "proposal",
    "software_copyright",
    "patent",
}
_ROLL_OUT_CONFIG_KEY = "rollout"
_CHAT_ORCHESTRATION_FLAG = "chat_feature_orchestration_enabled"


def _workspace_rollout_config(workspace: Workspace) -> dict[str, Any]:
    config = getattr(workspace, "config", {}) or {}
    rollout = config.get(_ROLL_OUT_CONFIG_KEY) if isinstance(config, dict) else {}
    return rollout if isinstance(rollout, dict) else {}


def is_workspace_chat_orchestration_enabled(workspace: Workspace) -> bool:
    """Return whether chat-driven feature orchestration is enabled."""
    workspace_type = resolve_workspace_type(workspace)
    rollout = _workspace_rollout_config(workspace)
    enabled = rollout.get(_CHAT_ORCHESTRATION_FLAG)
    if isinstance(enabled, bool):
        return enabled
    return workspace_type in _CHAT_ROLLOUT_DEFAULT_TYPES


def _select_feature_by_skill(
    workspace_type: str,
    selected_skill: str | None,
) -> FeatureIntent | None:
    if not selected_skill:
        return None
    mapping = _SKILL_TO_FEATURE.get(workspace_type, {})
    entry = mapping.get(selected_skill)
    if not entry:
        return None
    feature_id, defaults = entry
    return FeatureIntent(feature_id=feature_id, params=dict(defaults))


def _select_feature_by_message(
    workspace_type: str,
    message: str,
) -> FeatureIntent | None:
    entry = _select_feature_by_message_entry(workspace_type, message)
    if entry is None:
        return None
    feature_id, defaults = entry
    return FeatureIntent(feature_id=feature_id, params=dict(defaults))


async def _resolve_feature_intent(
    *,
    workspace: Workspace,
    message: str,
    selected_skill: str | None,
) -> FeatureIntent | None:
    workspace_type = resolve_workspace_type(workspace)
    intent = _select_feature_by_skill(workspace_type, selected_skill)
    if intent is None and _message_has_action_intent(message):
        intent = _select_feature_by_message(workspace_type, message)
    if intent is None:
        return None

    params, missing_reason, missing_feature_id = await _resolve_feature_params(
        feature_id=intent.feature_id,
        params=intent.params,
        workspace_type=workspace_type,
        workspace=workspace,
        message=message,
        load_latest_draft_summary=_load_latest_draft_summary,
    )
    intent.params = params
    intent.missing_reason = missing_reason
    intent.missing_feature_id = missing_feature_id
    return intent


async def _execute_workspace_feature_request(
    *,
    db: Any,
    workspace: Workspace,
    workspace_service: WorkspaceService,
    feature_id: str,
    params: Mapping[str, Any] | None,
    thread_id: str | None,
    user_id: str,
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
    require_chat_orchestration: bool = False,
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
        if require_chat_orchestration and not is_workspace_chat_orchestration_enabled(
            workspace
        ):
            return None

        return await _execute_workspace_feature_request(
            db=db,
            workspace=workspace,
            workspace_service=workspace_service,
            feature_id=feature_id,
            params=params,
            thread_id=thread_id,
            user_id=user_id,
        )


async def maybe_bridge_workspace_feature(
    *,
    message: str,
    workspace_id: str | None,
    thread_id: str | None,
    user_id: str,
    selected_skill: str | None,
) -> BridgedChatResponse | None:
    """Try to convert a chat turn into a canonical workspace feature execution."""
    if not workspace_id:
        return None

    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        workspace = await workspace_service.get(workspace_id)
        if workspace is None:
            return None
        if str(workspace.user_id) != str(user_id):
            logger.warning(
                "Skipping feature bridge for unowned workspace %s and user %s",
                workspace_id,
                user_id,
            )
            return None
        if not is_workspace_chat_orchestration_enabled(workspace):
            return None

        intent = await _resolve_feature_intent(
            workspace=workspace,
            message=message,
            selected_skill=selected_skill,
        )
        if intent is None:
            return None
        if intent.missing_reason:
            return _build_missing_response(
                feature_id=intent.feature_id,
                message=intent.missing_reason,
                missing_feature_id=intent.missing_feature_id,
            )

        return await _execute_workspace_feature_request(
            db=db,
            workspace=workspace,
            workspace_service=workspace_service,
            feature_id=intent.feature_id,
            params=intent.params,
            thread_id=thread_id,
            user_id=user_id,
        )


def _coerce_task_params(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return coerce_workspace_feature_params(payload)
