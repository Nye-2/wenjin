"""Focused tests for thread runtime config propagation."""

from __future__ import annotations

from types import SimpleNamespace

from src.application.handlers.thread_turn_handler import (
    _maybe_attach_intake_spec_fallback,
    _resolve_workspace_id,
    build_thread_initial_state,
    build_thread_runtime_config,
)
from src.application.results import GeneratedThreadReply, ThreadTurnRequest


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


def test_workbench_intake_entry_does_not_seed_auto_launch_feature_id() -> None:
    request = ThreadTurnRequest(
        message="我想使用软著申报材料包",
        metadata={
            "workbench_launch": {
                "capability_id": "software_copyright_application_pack",
                "capability_name": "软著申报材料包",
                "mode": "intake",
            }
        },
    )
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

    assert "launch_feature_id" not in config["configurable"]


def test_super_workflow_entry_seed_does_not_seed_auto_launch_without_spec_approval() -> None:
    request = ThreadTurnRequest(
        message="请帮我开始「软著申报材料包」。",
        metadata={
            "entry_seed": {
                "feature_id": "software_copyright_application_pack",
                "params": {},
            },
            "orchestration": {
                "feature_id": "software_copyright_application_pack",
                "source": "workspace_entry",
                "params": {},
            },
        },
    )
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

    assert "launch_feature_id" not in config["configurable"]


def test_super_workflow_spec_approval_can_seed_auto_launch() -> None:
    request = ThreadTurnRequest(
        message="同意并开始执行这份 Spec。",
        metadata={
            "orchestration": {
                "feature_id": "software_copyright_application_pack",
                "params": {"software_name": "智慧排课系统"},
            },
            "intake_spec_launch": {
                "spec_id": "intake-1",
                "revision": 2,
            },
        },
    )
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

    assert config["configurable"]["launch_feature_id"] == "software_copyright_application_pack"


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


def test_intake_spec_fallback_attaches_ready_software_spec() -> None:
    request = ThreadTurnRequest(
        message=(
            "软件名称：智课云排课系统 V1.0。类型：Web 系统。后端语言 Java。"
            "核心功能包括自动排课、教师冲突检测、统计报表。可以开始写 Spec。"
        ),
        workspace_id="ws-1",
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        workspace_type="software_copyright",
    )
    reply = GeneratedThreadReply(content="已整理好 Spec。")

    result = _maybe_attach_intake_spec_fallback(
        reply,
        request=request,
        thread=thread,
        conversation_messages=[
            {
                "role": "user",
                "content": "软件名称：旧系统 V1.0。类型：Web 系统。核心功能包括旧功能。可以开始写 Spec。",
            }
        ],
    )

    block = result.blocks[-1]
    spec = block["output"]["intake_spec"]
    assert block["tool"] == "draft_intake_spec"
    assert spec["status"] == "ready"
    assert spec["workspace_type"] == "software_copyright"
    assert spec["capability_id"] == "software_copyright_application_pack"
    assert spec["params"]["software_name"] == "智课云排课系统 V1.0"
    assert spec["params"]["software_type"] == "web"
    assert spec["params"]["backend_language"] == "Java"
    assert spec["params"]["visual_strategy"]["ui_screenshots"] == "static_frontend_screenshot"


def test_intake_spec_fallback_for_math_modeling_defaults_python() -> None:
    request = ThreadTurnRequest(
        message=(
            "赛题：某城市需要根据历史交通流量预测早晚高峰拥堵指数，"
            "请建立模型并生成论文包，可以开始写 Spec。"
        ),
        workspace_id="ws-1",
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        workspace_type="math_modeling",
    )
    reply = GeneratedThreadReply(content="")

    result = _maybe_attach_intake_spec_fallback(
        reply,
        request=request,
        thread=thread,
        conversation_messages=[],
    )

    spec = result.blocks[-1]["output"]["intake_spec"]
    assert spec["status"] == "ready"
    assert spec["workspace_type"] == "math_modeling"
    assert spec["capability_id"] == "math_modeling_paper_pack"
    assert spec["params"]["programming_language"] == "python"
    assert "Python" in spec["markdown"]


def test_intake_spec_fallback_does_not_affect_plain_chat() -> None:
    request = ThreadTurnRequest(message="解释一下什么是软著。", workspace_id="ws-1")
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        workspace_type="software_copyright",
    )
    reply = GeneratedThreadReply(content="软件著作权是...")

    result = _maybe_attach_intake_spec_fallback(
        reply,
        request=request,
        thread=thread,
        conversation_messages=[],
    )

    assert result.blocks == []
