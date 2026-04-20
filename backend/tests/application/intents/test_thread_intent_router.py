"""Tests for deterministic thread intent routing."""

from __future__ import annotations

from types import SimpleNamespace

from src.application.intents import ThreadIntentRouter
from src.application.results import ThreadTurnRequest


def _workspace(workspace_type: str):
    return SimpleNamespace(type=workspace_type)


def test_seeded_feature_applies_explicit_skill_defaults() -> None:
    request = ThreadTurnRequest(
        message="请开始吧",
        workspace_id="ws-1",
        skill="framework-designer",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "thesis_writing",
                "params": {},
            }
        },
    )

    decision = ThreadIntentRouter.route(
        request=request,
        workspace=_workspace("thesis"),
    )

    assert decision.mode == "launch_feature"
    assert decision.reason == "explicit_launch_intent"
    assert decision.feature_id == "thesis_writing"
    assert decision.skill_id == "framework-designer"
    assert decision.params.get("action") == "generate_outline"


def test_seeded_feature_rejects_skill_feature_mismatch() -> None:
    request = ThreadTurnRequest(
        message="开始执行",
        workspace_id="ws-1",
        skill="deep-research",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "thesis_writing",
                "params": {},
            }
        },
    )

    decision = ThreadIntentRouter.route(
        request=request,
        workspace=_workspace("thesis"),
    )

    assert decision.mode == "free_thread"
    assert decision.reason == "skill_feature_mismatch"
    assert decision.feature_id is None
    assert decision.skill_id is None


def test_resume_intent_routes_to_resume_feature_mode() -> None:
    request = ThreadTurnRequest(
        message="继续执行",
        workspace_id="ws-1",
        metadata={
            "orchestration": {
                "intent": "resume",
                "execution_session_id": "exec-1",
                "params": {"topic": "LLM planning"},
            }
        },
    )

    decision = ThreadIntentRouter.route(
        request=request,
        workspace=_workspace("thesis"),
    )

    assert decision.mode == "resume_feature"
    assert decision.reason == "explicit_resume_intent"
    assert decision.feature_id is None
    assert decision.params["topic"] == "LLM planning"


def test_unseeded_message_without_intent_stays_free_thread() -> None:
    request = ThreadTurnRequest(
        message="开始写全篇论文",
        workspace_id="ws-1",
    )

    decision = ThreadIntentRouter.route(
        request=request,
        workspace=_workspace("thesis"),
    )

    assert decision.mode == "free_thread"
    assert decision.reason == "no_orchestration_intent"


def test_seed_without_intent_stays_free_thread() -> None:
    request = ThreadTurnRequest(
        message="请帮我开始「框架与摘要」。",
        workspace_id="ws-1",
        metadata={
            "orchestration": {
                "feature_id": "framework_outline",
                "params": {"topic": "LLM planning"},
            }
        },
    )

    decision = ThreadIntentRouter.route(
        request=request,
        workspace=_workspace("sci"),
    )

    assert decision.mode == "free_thread"
    assert decision.reason == "no_orchestration_intent"
