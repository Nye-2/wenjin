"""Route a prepared chat turn before invoking the lead agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.application.intents import ThreadIntentDecision, ThreadIntentRouter
from src.application.results import ThreadTurnRequest


class ChatTurnMode(StrEnum):
    """Canonical turn modes for chat ingress."""

    PURE_CHAT = "pure_chat"
    FEATURE_LAUNCH = "feature_launch"
    FEATURE_RESUME = "feature_resume"
    FEATURE_STATUS = "feature_status"
    FEATURE_PROPOSAL = "feature_proposal"


@dataclass(frozen=True, slots=True)
class ChatTurnRoute:
    """Resolved route for one chat turn."""

    mode: ChatTurnMode
    orchestration: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_feature_command(self) -> bool:
        return self.mode in {
            ChatTurnMode.FEATURE_LAUNCH,
            ChatTurnMode.FEATURE_RESUME,
        }

    @property
    def feature_id(self) -> str | None:
        return _optional_str(self.orchestration.get("feature_id"))

    @property
    def execution_session_id(self) -> str | None:
        return _optional_str(self.orchestration.get("execution_session_id"))

    @property
    def skill_id(self) -> str | None:
        return _optional_str(self.orchestration.get("skill_id") or self.orchestration.get("entry_skill_id"))

    @property
    def params(self) -> dict[str, Any]:
        params = self.orchestration.get("params")
        return dict(params) if isinstance(params, Mapping) else {}


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _read_orchestration(request: ThreadTurnRequest) -> Mapping[str, Any]:
    metadata = request.metadata if isinstance(request.metadata, Mapping) else None
    orchestration = metadata.get("orchestration") if metadata is not None else None
    return orchestration if isinstance(orchestration, Mapping) else {}


def _thread_workspace_type(thread: Any) -> str | None:
    workspace_type = _optional_str(getattr(thread, "workspace_type", None))
    if workspace_type:
        return workspace_type

    # Avoid triggering a lazy SQLAlchemy relationship load. ThreadService attaches
    # workspace_type during normal production reads; this fallback is for tests or
    # already-hydrated objects only.
    thread_dict = getattr(thread, "__dict__", {})
    workspace = thread_dict.get("workspace") if isinstance(thread_dict, dict) else None
    return _optional_str(getattr(workspace, "type", None))


def _orchestration_from_decision(
    *,
    request: ThreadTurnRequest,
    decision: ThreadIntentDecision,
    intent: str,
) -> Mapping[str, Any]:
    orchestration = dict(_read_orchestration(request))
    orchestration["intent"] = intent
    if decision.feature_id is not None:
        orchestration["feature_id"] = decision.feature_id
    if decision.execution_session_id is not None:
        orchestration["execution_session_id"] = decision.execution_session_id
    if decision.skill_id is not None:
        orchestration["skill_id"] = decision.skill_id
    orchestration["params"] = dict(decision.params)
    return orchestration


class ChatTurnRouter:
    """Thin adapter from chat ingress to the canonical thread intent router."""

    @staticmethod
    def route(request: ThreadTurnRequest, thread: Any) -> ChatTurnRoute:
        decision = ThreadIntentRouter.route(
            request=request,
            workspace_type=_thread_workspace_type(thread),
        )
        if decision.mode == "resume_feature":
            return ChatTurnRoute(
                mode=ChatTurnMode.FEATURE_RESUME,
                orchestration=_orchestration_from_decision(
                    request=request,
                    decision=decision,
                    intent="resume",
                ),
            )
        if decision.mode == "launch_feature":
            return ChatTurnRoute(
                mode=ChatTurnMode.FEATURE_LAUNCH,
                orchestration=_orchestration_from_decision(
                    request=request,
                    decision=decision,
                    intent="launch",
                ),
            )
        return ChatTurnRoute(mode=ChatTurnMode.PURE_CHAT)
