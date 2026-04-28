"""Route a prepared chat turn before invoking the lead agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

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
        return _optional_str(
            self.orchestration.get("skill_id")
            or self.orchestration.get("entry_skill_id")
        )

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


class ChatTurnRouter:
    """Classify a turn as pure chat or a feature command."""

    @staticmethod
    def route(request: ThreadTurnRequest, thread: Any) -> ChatTurnRoute:
        _ = thread
        orchestration = _read_orchestration(request)
        intent = str(orchestration.get("intent") or "").strip().lower()
        if intent == "resume":
            return ChatTurnRoute(
                mode=ChatTurnMode.FEATURE_RESUME,
                orchestration=orchestration,
            )
        if intent == "launch":
            return ChatTurnRoute(
                mode=ChatTurnMode.FEATURE_LAUNCH,
                orchestration=orchestration,
            )
        return ChatTurnRoute(mode=ChatTurnMode.PURE_CHAT)

