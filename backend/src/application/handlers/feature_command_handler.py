"""Feature command handling for chat ingress.

This handler intentionally bypasses the lead-agent tool loop. Explicit
launch/resume requests go straight into the canonical feature ingress.
"""

from __future__ import annotations

from typing import Any

from src.application.errors import PaymentRequiredError
from src.application.handlers.chat_turn_router import (
    ChatTurnMode,
    ChatTurnRoute,
)
from src.application.presenters.thread_feature_cards import build_feature_proposal_response
from src.application.results import GeneratedThreadReply, ThreadTurnRequest
from src.application.services.thread_feature_service import (
    execute_workspace_feature_request,
)
from src.workspace_features import get_workspace_feature
from src.workspace_features.skills import get_skill_by_id


def _warning_reply(
    *,
    message: str,
    feature_id: str | None = None,
    execution_session_id: str | None = None,
    status: str = "warning",
    code: str = "feature_command_invalid",
) -> GeneratedThreadReply:
    return GeneratedThreadReply(
        content=message,
        blocks=[
            {
                "type": "warning",
                "title": "Feature command not started",
                "data": {
                    "code": code,
                    "feature_id": feature_id,
                    "execution_session_id": execution_session_id,
                    "detail": message,
                },
            }
        ],
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "execution_session_id": execution_session_id,
                "status": status,
                "warning": code,
            }
        },
    )


class FeatureCommandHandler:
    """Adapter from chat turn commands to FeatureIngressService."""

    async def handle(
        self,
        *,
        request: ThreadTurnRequest,
        thread: Any,
        actor_id: str,
        route: ChatTurnRoute,
    ) -> GeneratedThreadReply:
        workspace_id = (
            str(getattr(thread, "workspace_id", "") or request.workspace_id or "").strip()
            or None
        )
        if workspace_id is None:
            return _warning_reply(
                message="当前对话未绑定 workspace，无法启动 feature 任务。",
                feature_id=route.feature_id,
                execution_session_id=route.execution_session_id,
                code="workspace_context_missing",
            )

        feature_id = route.feature_id
        execution_session_id = route.execution_session_id
        if route.mode == ChatTurnMode.FEATURE_PROPOSAL:
            workspace_type = str(getattr(thread, "workspace_type", "") or "").strip()
            if not workspace_type or not feature_id:
                return _warning_reply(
                    message="当前对话缺少 workspace 类型或 feature_id，无法生成启动建议。",
                    feature_id=feature_id,
                    code="feature_proposal_context_missing",
                )
            feature = get_workspace_feature(workspace_type, feature_id)
            if feature is None:
                return _warning_reply(
                    message="当前 workspace 不支持这个 feature，无法生成启动建议。",
                    feature_id=feature_id,
                    code="feature_proposal_unavailable",
                )
            skill_id = route.skill_id
            if skill_id is None:
                skill_id = getattr(thread, "skill", None) or request.skill
            skill_def = get_skill_by_id(workspace_type, str(skill_id).strip()) if skill_id else None
            if skill_def is not None and skill_def.feature_id != feature_id:
                skill_id = None
            return build_feature_proposal_response(
                feature_id=feature_id,
                feature_name=str(getattr(feature, "name", "") or feature_id),
                skill_id=str(skill_id).strip() if skill_id else None,
                params=route.params,
                reason=str(route.orchestration.get("reason") or "feature_intent_detected"),
                confidence=float(route.orchestration.get("confidence") or 0),
            )

        if route.mode == ChatTurnMode.FEATURE_LAUNCH and not feature_id:
            return _warning_reply(
                message="缺少 feature_id，无法启动 feature 任务。",
                execution_session_id=execution_session_id,
                code="feature_id_missing",
            )
        if route.mode == ChatTurnMode.FEATURE_RESUME and not execution_session_id:
            return _warning_reply(
                message="缺少 execution_session_id，无法继续 feature 任务。",
                feature_id=feature_id,
                code="execution_session_missing",
            )

        skill_id = route.skill_id or getattr(thread, "skill", None) or request.skill
        try:
            reply = await execute_workspace_feature_request(
                workspace_id=workspace_id,
                thread_id=str(thread.id),
                user_id=actor_id,
                feature_id=feature_id,
                params=route.params,
                skill_id=str(skill_id).strip() if skill_id else None,
                launch_message=request.message,
                execution_session_id=execution_session_id,
            )
        except PaymentRequiredError as exc:
            return _warning_reply(
                message=exc.message,
                feature_id=feature_id,
                execution_session_id=execution_session_id,
                status="payment_required",
                code="feature_budget_exhausted",
            )
        if reply is None:
            return _warning_reply(
                message="当前 feature 任务无法启动，请检查 workspace 和权限上下文。",
                feature_id=feature_id,
                execution_session_id=execution_session_id,
                code="feature_command_unavailable",
            )
        return reply
