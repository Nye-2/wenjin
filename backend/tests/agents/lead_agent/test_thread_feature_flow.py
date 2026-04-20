"""Tests for thread feature card builders and catalog helpers."""

from types import SimpleNamespace

import pytest

from src.agents.lead_agent import thread_feature_catalog
from src.agents.lead_agent.thread_feature_cards import (
    build_confirmation_required_response,
    build_feature_task_completion_card,
    build_feature_task_failure_card,
)
from src.agents.lead_agent.thread_feature_presenters import feature_title
from src.task.workspace_feature_params import coerce_workspace_feature_params
from src.workspace_features import iter_workspace_features


def test_build_feature_task_completion_card_preserves_params_and_actions() -> None:
    reply = build_feature_task_completion_card(
        feature_id="framework_outline",
        task_id="task-123",
        execution_session_id="exec-123",
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
    assert reply.metadata["orchestration"]["execution_session_id"] == "exec-123"
    assert reply.metadata["orchestration"]["params"]["context_artifact_ids"] == ["artifact-1"]
    assert reply.metadata["orchestration"]["suggested_follow_up"]
    assert "LLM Framework" in reply.content
    assert reply.blocks[1]["type"] == "result"
    next_steps = reply.blocks[2]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "open_feature",
        "continue_thread",
        "rerun_from_artifact",
    ]


def test_coerce_task_params_preserves_rerun_fields_used_by_frontend_actions() -> None:
    params = coerce_workspace_feature_params(
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


def test_coerce_task_params_returns_empty_without_canonical_params() -> None:
    params = coerce_workspace_feature_params({"paper_title": "Agent Paper"})

    assert params == {}


def test_build_feature_task_failure_card_exposes_retry_actions() -> None:
    reply = build_feature_task_failure_card(
        feature_id="peer_review",
        task_id="task-456",
        execution_session_id="exec-456",
        payload={"params": {"paper_title": "Agent Paper"}},
        error="tool timeout",
    )

    assert reply.metadata["orchestration"]["status"] == "failed"
    assert reply.metadata["orchestration"]["execution_session_id"] == "exec-456"
    assert reply.metadata["orchestration"]["error"] == "tool timeout"
    assert reply.blocks[0]["type"] == "warning"
    next_steps = reply.blocks[1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "open_feature",
        "continue_thread",
        "rerun_from_artifact",
    ]


def test_build_confirmation_required_response_marks_confirmation_status() -> None:
    reply = build_confirmation_required_response(
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
    )

    assert reply.metadata["orchestration"]["status"] == "confirmation_required"
    assert reply.metadata["orchestration"]["feature_id"] == "framework_outline"
    assert reply.metadata["orchestration"]["params"]["topic"] == "LLM planning"
    assert "开始吧" in reply.content


def test_feature_titles_cover_workspace_registry() -> None:
    for feature in iter_workspace_features():
        assert feature_title(feature.id)
        assert feature_title(feature.id) != feature.id


@pytest.mark.asyncio
async def test_build_workspace_feature_overview_includes_skill_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeWorkspaceService:
        def __init__(self, db):
            self._workspace = SimpleNamespace(
                id="ws-1",
                user_id="user-1",
                type="sci",
            )

        async def get(self, workspace_id: str):
            return self._workspace

    monkeypatch.setattr(thread_feature_catalog, "get_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(thread_feature_catalog, "WorkspaceService", _FakeWorkspaceService)

    overview = await thread_feature_catalog.build_workspace_feature_overview(
        "ws-1",
        user_id="user-1",
    )

    assert overview is not None
    framework_feature = next(
        feature for feature in overview["features"] if feature["id"] == "framework_outline"
    )
    assert framework_feature["defaultSkillId"] == "framework-designer"
    assert "framework-designer" in framework_feature["entrySkillIds"]
