"""Tests for thread feature card builders and catalog helpers."""

from types import SimpleNamespace

import pytest

from src.application.presenters.thread_feature_cards import (
    build_feature_task_completion_card,
    build_feature_task_failure_card,
)
from src.application.presenters.thread_feature_presenters import feature_title
from src.task.workspace_feature_params import coerce_workspace_feature_params
from src.workspace_features import iter_workspace_features, thread_catalog


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
    assert reply.blocks[0]["type"] == "task_result"
    next_steps = reply.blocks[-1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "open_feature",
        "continue_thread",
        "rerun_from_artifact",
    ]


def test_build_feature_task_completion_card_prioritizes_prism_review() -> None:
    reply = build_feature_task_completion_card(
        feature_id="writing",
        task_id="task-prism",
        execution_session_id="exec-prism",
        payload={"params": {"section": "introduction"}},
        result={
            "data": {
                "latex_project_id": "project-1",
                "project_name": "Agent Paper",
                "main_file": "main.tex",
                "pending_file_changes": 2,
                "applied_file_changes": 0,
                "compile_status": "blocked_by_review",
                "prism_url": "/latex/project-1",
            },
            "artifacts": [{"id": "artifact-1", "title": "Introduction draft"}],
        },
    )

    assert reply.blocks[0]["type"] == "task_result"
    assert reply.blocks[0]["data"]["prism"]["pending_file_changes"] == 2
    assert reply.blocks[1]["type"] == "prism_status"
    assert reply.blocks[1]["data"]["url"] == "/latex/project-1"
    next_steps = reply.blocks[-1]["data"]["items"]
    assert [item["action"] for item in next_steps[:2]] == [
        "preview_prism_changes",
        "open_prism",
    ]
    assert next_steps[0]["params"]["project_id"] == "project-1"


def test_build_literature_search_completion_card_exposes_evidence_and_reference_destination() -> None:
    reply = build_feature_task_completion_card(
        feature_id="literature_search",
        task_id="task-lit",
        execution_session_id="exec-lit",
        payload={"params": {"query": "agent planning"}},
        result={
            "data": {
                "query": "agent planning",
                "source": "semantic_scholar",
                "retrieval": {
                    "status": "ok",
                    "query": "agent planning",
                    "verified_at": "2026-04-30T00:00:00+00:00",
                },
                "verified_papers": [
                    {
                        "title": "Verified Paper",
                        "year": 2025,
                        "venue": "ACL",
                        "doi": "10.1000/verified",
                        "external_id": "ss-1",
                        "citations_count": 12,
                    }
                ],
                    "model_synthesis": {"summary": "grounded"},
                    "unverified_leads": [{"lead": "next query"}],
                    "reference_import": {"imported": 1, "created": 1, "items": []},
                },
                "artifacts": [{"id": "artifact-lit", "title": "Literature search"}],
            },
    )

    task_result = reply.blocks[0]
    assert task_result["type"] == "task_result"
    trust = task_result["data"]["trust"]
    assert trust["evidence_source_id"] == "semantic_scholar"
    assert trust["verified_papers_count"] == 1
    assert trust["unverified_leads_count"] == 1
    assert trust["verified_papers_preview"][0]["external_id"] == "ss-1"
    assert "literature_import" not in task_result["data"]
    assert task_result["data"]["reference_import"] is None
    assert {
        "kind": "references",
        "label": "参考库已同步 1 条 Semantic Scholar 文献",
    } in task_result["data"]["destinations"]
    next_steps = reply.blocks[-1]["data"]["items"]
    assert "import_references" not in [item["action"] for item in next_steps]


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
    assert reply.blocks[0]["type"] == "task_failure"
    recovery_actions = reply.blocks[0]["data"]["recovery_actions"]
    assert [item["action"] for item in recovery_actions] == [
        "resume_execution",
        "continue_thread",
    ]
    assert reply.blocks[1]["type"] == "warning"
    next_steps = reply.blocks[-1]["data"]["items"]
    assert [item["action"] for item in next_steps] == [
        "continue_thread",
        "rerun_from_artifact",
    ]


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

    monkeypatch.setattr(thread_catalog, "get_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(thread_catalog, "WorkspaceService", _FakeWorkspaceService)

    overview = await thread_catalog.build_workspace_feature_overview(
        "ws-1",
        user_id="user-1",
    )

    assert overview is not None
    framework_feature = next(
        feature for feature in overview["features"] if feature["id"] == "framework_outline"
    )
    assert framework_feature["defaultSkillId"] == "framework-designer"
    assert "framework-designer" in framework_feature["entrySkillIds"]
