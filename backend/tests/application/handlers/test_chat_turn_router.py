"""Tests for chat control-plane turn routing."""

from __future__ import annotations

from types import SimpleNamespace

from src.application.handlers.chat_turn_router import ChatTurnMode, ChatTurnRouter
from src.application.results import ThreadTurnRequest


def test_router_detects_feature_launch() -> None:
    request = ThreadTurnRequest(
        message="开始",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "framework_outline",
                "params": {"topic": "LLM planning"},
            }
        },
    )

    route = ChatTurnRouter.route(
        request,
        SimpleNamespace(id="thread-1", workspace_type="sci"),
    )

    assert route.mode == ChatTurnMode.FEATURE_LAUNCH
    assert route.is_feature_command is True
    assert route.feature_id == "framework_outline"
    assert route.params == {"topic": "LLM planning"}


def test_router_detects_feature_resume() -> None:
    request = ThreadTurnRequest(
        message="继续",
        metadata={
            "orchestration": {
                "intent": "resume",
                "execution_session_id": "exec-1",
                "entry_skill_id": "deep-research",
            }
        },
    )

    route = ChatTurnRouter.route(request, SimpleNamespace(id="thread-1"))

    assert route.mode == ChatTurnMode.FEATURE_RESUME
    assert route.is_feature_command is True
    assert route.execution_session_id == "exec-1"
    assert route.skill_id == "deep-research"


def test_router_keeps_unstructured_turn_as_pure_chat() -> None:
    request = ThreadTurnRequest(
        message="帮我分析一下研究设计",
        metadata={"orchestration": {"intent": "suggest"}},
    )

    route = ChatTurnRouter.route(request, SimpleNamespace(id="thread-1"))

    assert route.mode == ChatTurnMode.PURE_CHAT
    assert route.is_feature_command is False


def test_router_applies_skill_defaults_from_intent_ssot() -> None:
    request = ThreadTurnRequest(
        message="开始",
        skill="framework-designer",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "thesis_writing",
                "params": {},
            }
        },
    )

    route = ChatTurnRouter.route(
        request,
        SimpleNamespace(id="thread-1", workspace_type="thesis"),
    )

    assert route.mode == ChatTurnMode.FEATURE_LAUNCH
    assert route.skill_id == "framework-designer"
    assert route.params == {"action": "generate_outline"}


def test_router_rejects_skill_feature_mismatch() -> None:
    request = ThreadTurnRequest(
        message="开始",
        skill="deep-research",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "thesis_writing",
                "params": {},
            }
        },
    )

    route = ChatTurnRouter.route(
        request,
        SimpleNamespace(id="thread-1", workspace_type="thesis"),
    )

    assert route.mode == ChatTurnMode.PURE_CHAT
    assert route.is_feature_command is False
