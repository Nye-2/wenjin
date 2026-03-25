"""Tests for structured chat feature bridge cards."""

from types import SimpleNamespace

import pytest

from src.agents.lead_agent import feature_bridge
from src.agents.lead_agent.feature_bridge import (
    BridgedChatResponse,
    FeatureIntent,
    build_feature_task_completion_card,
    build_feature_task_failure_card,
)
from src.agents.lead_agent.feature_bridge_presenters import feature_title
from src.workspace_features import iter_workspace_features


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeWorkspaceService:
    def __init__(self, db, workspace):
        self._workspace = workspace

    async def get(self, workspace_id: str):
        return self._workspace


def _patch_common_dependencies(monkeypatch: pytest.MonkeyPatch, workspace: SimpleNamespace) -> None:
    monkeypatch.setattr(feature_bridge, "get_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(
        feature_bridge,
        "WorkspaceService",
        lambda db: _FakeWorkspaceService(db, workspace),
    )
    monkeypatch.setattr(feature_bridge, "TaskStore", lambda *args, **kwargs: object())
    monkeypatch.setattr(feature_bridge, "TaskService", lambda *args, **kwargs: object())
    monkeypatch.setattr(feature_bridge, "LiteratureService", lambda *args, **kwargs: object())
    monkeypatch.setattr(feature_bridge, "CreditService", lambda *args, **kwargs: object())
    monkeypatch.setattr(feature_bridge.redis_settings, "enabled", False)


@pytest.mark.asyncio
async def test_bridge_missing_response_uses_action_typed_next_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = SimpleNamespace(
        id="ws-1",
        user_id="user-1",
        type="sci",
        config={"rollout": {"chat_feature_orchestration_enabled": True}},
    )
    _patch_common_dependencies(monkeypatch, workspace)
    async def _fake_resolve_feature_intent(**kwargs):
        return FeatureIntent(
            feature_id="framework_outline",
            missing_reason="缺少用于生成框架的研究主题。",
            missing_feature_id="literature_review",
        )

    monkeypatch.setattr(
        feature_bridge,
        "_resolve_feature_intent",
        _fake_resolve_feature_intent,
    )

    reply = await feature_bridge.maybe_bridge_workspace_feature(
        message="帮我生成框架",
        workspace_id="ws-1",
        thread_id="thread-1",
        user_id="user-1",
        selected_skill=None,
    )

    assert reply is not None
    next_steps = reply.blocks[1]["data"]["items"]
    assert next_steps[0]["feature_id"] == "literature_review"
    assert next_steps[0]["action"] == "trigger_feature"
    assert next_steps[1]["feature_id"] == "framework_outline"
    assert next_steps[1]["action"] == "continue_chat"


@pytest.mark.asyncio
async def test_bridge_task_response_exposes_chat_card_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = SimpleNamespace(
        id="ws-2",
        user_id="user-1",
        type="sci",
        config={"rollout": {"chat_feature_orchestration_enabled": True}},
    )
    _patch_common_dependencies(monkeypatch, workspace)

    async def _fake_resolve_feature_intent(**kwargs):
        return FeatureIntent(
            feature_id="framework_outline",
            params={"topic": "LLM planning"},
        )

    class _FakeHandler:
        def __init__(self, **kwargs):
            pass

        async def execute(self, *args, **kwargs):
            return SimpleNamespace(
                task_id="task-123",
                message="任务已提交",
            )

    monkeypatch.setattr(feature_bridge, "_resolve_feature_intent", _fake_resolve_feature_intent)
    monkeypatch.setattr(feature_bridge, "FeatureExecutionHandler", _FakeHandler)

    reply = await feature_bridge.maybe_bridge_workspace_feature(
        message="生成论文框架",
        workspace_id="ws-2",
        thread_id="thread-2",
        user_id="user-1",
        selected_skill=None,
    )

    assert reply is not None
    assert reply.metadata["orchestration"]["feature_id"] == "framework_outline"
    next_steps = reply.blocks[1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "continue_chat",
        "open_feature",
        "rerun_from_artifact",
    ]


@pytest.mark.asyncio
async def test_bridge_delegates_resolved_feature_to_shared_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = SimpleNamespace(
        id="ws-2",
        user_id="user-1",
        type="sci",
        config={"rollout": {"chat_feature_orchestration_enabled": True}},
    )
    _patch_common_dependencies(monkeypatch, workspace)

    async def _fake_resolve_feature_intent(**kwargs):
        return FeatureIntent(
            feature_id="framework_outline",
            params={"topic": "LLM planning"},
        )

    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return BridgedChatResponse(
            content="shared executor response",
            metadata={"orchestration": {"feature_id": kwargs["feature_id"]}},
        )

    monkeypatch.setattr(feature_bridge, "_resolve_feature_intent", _fake_resolve_feature_intent)
    monkeypatch.setattr(
        feature_bridge,
        "_execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    reply = await feature_bridge.maybe_bridge_workspace_feature(
        message="生成论文框架",
        workspace_id="ws-2",
        thread_id="thread-2",
        user_id="user-1",
        selected_skill=None,
    )

    assert reply is not None
    assert reply.content == "shared executor response"
    assert captured["feature_id"] == "framework_outline"
    assert captured["params"] == {"topic": "LLM planning"}
    assert captured["thread_id"] == "thread-2"
    assert captured["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_bridge_warning_response_exposes_open_and_continue_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = SimpleNamespace(
        id="ws-3",
        user_id="user-1",
        type="thesis",
        config={"rollout": {"chat_feature_orchestration_enabled": True}},
    )
    _patch_common_dependencies(monkeypatch, workspace)

    async def _fake_resolve_feature_intent(**kwargs):
        return FeatureIntent(feature_id="thesis_writing", params={"action": "write_all"})

    class _FakeHandler:
        def __init__(self, **kwargs):
            pass

        async def execute(self, *args, **kwargs):
            return SimpleNamespace(
                task_id=None,
                code="literature_insufficient",
                detail={"current": 2, "recommended": 15},
                message="文献数量不足",
            )

    monkeypatch.setattr(feature_bridge, "_resolve_feature_intent", _fake_resolve_feature_intent)
    monkeypatch.setattr(feature_bridge, "FeatureExecutionHandler", _FakeHandler)

    reply = await feature_bridge.maybe_bridge_workspace_feature(
        message="开始写论文",
        workspace_id="ws-3",
        thread_id="thread-3",
        user_id="user-1",
        selected_skill=None,
    )

    assert reply is not None
    assert reply.metadata["orchestration"]["status"] == "warning"
    next_steps = reply.blocks[1]["data"]["items"]
    assert next_steps[0]["feature_id"] == "literature_management"
    assert next_steps[0]["action"] == "open_feature"
    assert next_steps[1]["feature_id"] == "thesis_writing"
    assert next_steps[1]["action"] == "continue_chat"


def test_build_feature_task_completion_card_preserves_params_and_actions() -> None:
    reply = build_feature_task_completion_card(
        feature_id="framework_outline",
        task_id="task-123",
        payload={"params": {"topic": "LLM planning", "context_artifact_ids": ["artifact-1"]}},
        result={
            "data": {
                "sections": [{"title": "Intro"}, {"title": "Method"}],
                "keywords": ["llm", "planning"],
            },
            "artifacts": [{"id": "artifact-2", "title": "LLM Framework"}],
        },
    )

    assert reply.metadata["orchestration"]["status"] == "completed"
    assert reply.metadata["orchestration"]["task_id"] == "task-123"
    assert reply.metadata["orchestration"]["params"]["context_artifact_ids"] == ["artifact-1"]
    assert "LLM Framework" in reply.content
    next_steps = reply.blocks[1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "open_feature",
        "continue_chat",
        "rerun_from_artifact",
    ]


def test_coerce_task_params_preserves_rerun_fields_used_by_frontend_actions() -> None:
    params = feature_bridge._coerce_task_params(
        {
            "params": {
                "manuscript_excerpt": "Draft body",
                "proposal_type": "nsfc",
                "period_months": 36,
                "industry_scope": "智能体系统",
                "type": "timeline",
                "fig_type": "timeline",
                "section": "discussion",
            }
        }
    )

    assert params["manuscript_excerpt"] == "Draft body"
    assert params["proposal_type"] == "nsfc"
    assert params["period_months"] == 36
    assert params["industry_scope"] == "智能体系统"
    assert params["type"] == "timeline"
    assert params["fig_type"] == "timeline"
    assert params["section"] == "discussion"


def test_build_feature_task_failure_card_exposes_retry_actions() -> None:
    reply = build_feature_task_failure_card(
        feature_id="peer_review",
        task_id="task-456",
        payload={"params": {"paper_title": "Agent Paper"}},
        error="tool timeout",
    )

    assert reply.metadata["orchestration"]["status"] == "failed"
    assert reply.metadata["orchestration"]["error"] == "tool timeout"
    assert reply.blocks[0]["type"] == "warning"
    next_steps = reply.blocks[1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "open_feature",
        "continue_chat",
        "rerun_from_artifact",
    ]


def test_feature_titles_cover_workspace_registry() -> None:
    for feature in iter_workspace_features():
        assert feature_title(feature.id)
        assert feature_title(feature.id) != feature.id


@pytest.mark.parametrize(
    ("workspace_type", "message", "expected_feature_id"),
    [
        ("patent", "生成专利框架", "patent_outline"),
        ("software_copyright", "生成技术说明书", "technical_description"),
        ("proposal", "生成专利框架", None),
    ],
)
def test_select_feature_by_message_respects_workspace_registry(
    workspace_type: str,
    message: str,
    expected_feature_id: str | None,
) -> None:
    intent = feature_bridge._select_feature_by_message(workspace_type, message)
    assert (intent.feature_id if intent else None) == expected_feature_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "message", "feature_id", "param_key"),
    [
        ("patent", "生成专利框架", "patent_outline", "innovation_description"),
        ("software_copyright", "生成技术说明书", "technical_description", "software_name"),
        ("sci", "写摘要，1200字", "writing", "section_type"),
    ],
)
async def test_resolve_feature_intent_covers_new_workspace_modules(
    workspace_type: str,
    message: str,
    feature_id: str,
    param_key: str,
) -> None:
    workspace = SimpleNamespace(
        id="ws-intent",
        type=workspace_type,
        name="多模态学术助手",
        description="用于实验验证与技术申请的项目工作区",
        discipline="computer_science",
    )

    intent = await feature_bridge._resolve_feature_intent(
        workspace=workspace,
        message=message,
        selected_skill=None,
    )

    assert intent is not None
    assert intent.feature_id == feature_id
    assert intent.params.get(param_key)


@pytest.mark.asyncio
async def test_opening_research_direct_message_uses_workspace_context() -> None:
    workspace = SimpleNamespace(
        id="ws-opening",
        type="thesis",
        name="大模型学术写作助手",
        description="研究多智能体协同写作的记忆与规划机制",
        discipline="computer_science",
    )

    intent = await feature_bridge._resolve_feature_intent(
        workspace=workspace,
        message="开始开题报告",
        selected_skill=None,
    )

    assert intent is not None
    assert intent.feature_id == "opening_research"
    assert intent.params["report_type"] == "opening_report"
    assert intent.params["topic"] == "研究多智能体协同写作的记忆与规划机制"


@pytest.mark.parametrize(
    "workspace_type",
    ["thesis", "sci", "proposal", "software_copyright", "patent"],
)
def test_chat_orchestration_enabled_by_default_for_all_workspace_types(
    workspace_type: str,
) -> None:
    workspace = SimpleNamespace(type=workspace_type, config={})
    assert feature_bridge.is_workspace_chat_orchestration_enabled(workspace) is True
