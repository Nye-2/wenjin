"""Focused tests for thread runtime config propagation."""

from __future__ import annotations

from types import SimpleNamespace

from src.application.handlers.thread_turn_handler import (
    _resolve_workspace_id,
    build_thread_initial_state,
    build_thread_runtime_config,
)
from src.application.results import ThreadTurnRequest


def test_build_thread_runtime_config_does_not_propagate_feature_orchestration() -> None:
    request = ThreadTurnRequest(
        message="启动论文大纲",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "framework_outline",
                "params": {"topic": "LLM planning"},
            }
        },
    )
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1")

    runtime = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id="user-1",
        workspace_id="ws-1",
        effective_skill=None,
        effective_model="gpt-5.2",
        execution_id="exec-1",
    )

    configurable = runtime["configurable"]
    assert configurable["thread_id"] == "thread-1"
    assert configurable["workspace_id"] == "ws-1"
    assert configurable["user_id"] == "user-1"
    assert configurable["execution_id"] == "exec-1"
    assert "orchestration_intent" not in configurable
    assert "orchestration_feature_id" not in configurable
    assert "orchestration_params" not in configurable


def test_build_thread_runtime_config_surfaces_sanitized_launch_feature_params() -> None:
    request = ThreadTurnRequest(
        message="继续基于这篇论文写作",
        metadata={
            "orchestration": {
                "feature_id": "writing",
                "params": {
                    "entry": "open",
                    "execution_id": "exec-1",
                    "paper_title": "Agent Paper",
                    "source_artifact_id": "artifact-2",
                    "context_artifact_ids": ["artifact-2", "artifact-3"],
                },
            }
        },
    )
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1")

    runtime = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id="user-1",
        workspace_id="ws-1",
        effective_skill="section-writer",
        effective_model="gpt-5.2",
        execution_id="exec-1",
    )

    configurable = runtime["configurable"]
    assert configurable["launch_feature_params"] == {
        "paper_title": "Agent Paper",
        "source_artifact_id": "artifact-2",
        "context_artifact_ids": ["artifact-2", "artifact-3"],
    }
    assert configurable["execution_id"] == "exec-1"
    assert "entry" not in configurable["launch_feature_params"]
    assert "execution_id" not in configurable["launch_feature_params"]


def test_thread_runtime_config_includes_user_message_id_for_launch_idempotency() -> None:
    request = ThreadTurnRequest(message="启动 SCI 文献定位", workspace_id="ws-1")
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1", skill=None, model=None)

    config = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id="user-1",
        workspace_id="ws-1",
        effective_skill=None,
        effective_model="mimo-v2.5-pro",
        execution_id=None,
        user_message_id="msg-123",
    )

    assert config["configurable"]["user_message_id"] == "msg-123"
    assert config["configurable"]["launch_idempotency_key"] == "launch_feature:thread-1:msg-123"


def test_build_thread_initial_state_includes_thread_and_user_ids() -> None:
    thread = SimpleNamespace(id="thread-1", messages=[], workspace_id="ws-1")

    initial_state = build_thread_initial_state(
        thread,
        actor_id="user-1",
        workspace_id="ws-1",
        effective_skill="framework-designer",
        attachments=(),
    )

    assert initial_state["thread_id"] == "thread-1"
    assert initial_state["user_id"] == "user-1"
    assert initial_state["workspace_id"] == "ws-1"
    assert initial_state["current_skill"] == "framework-designer"


def test_resolve_workspace_id_prefers_thread_binding() -> None:
    request = ThreadTurnRequest(
        message="继续",
        workspace_id="ws-request",
    )
    thread = SimpleNamespace(workspace_id="ws-thread")

    resolved = _resolve_workspace_id(request, thread)

    assert resolved == "ws-thread"
