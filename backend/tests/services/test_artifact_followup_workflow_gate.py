"""Artifact follow-up workflow release gate tests."""

from src.application.presenters.thread_feature_cards import (
    build_feature_task_completion_card,
)
from src.database.models.artifact import Artifact
from src.database.models.workspace import Workspace, WorkspaceType
from src.services.feature_action_resolution_service import resolve_feature_action_state
from src.services.workspace_activity_contracts import build_task_activity_item


def test_completion_card_exposes_artifact_open_and_rerun_seed() -> None:
    reply = build_feature_task_completion_card(
        feature_id="framework_outline",
        task_id="task-artifact",
        execution_session_id="exec-artifact",
        payload={
            "params": {
                "topic": "LLM planning",
                "context_artifact_ids": ["artifact-previous"],
                "__internal_trace": "hidden",
            }
        },
        result={
            "data": {
                "sections": [{"title": "Intro"}, {"title": "Method"}],
                "keywords": ["llm", "planning"],
            },
            "artifacts": [{"id": "artifact-current", "title": "LLM Framework"}],
        },
    )

    task_result = reply.blocks[0]
    assert task_result["type"] == "task_result"
    assert {
        "kind": "artifact",
        "label": "LLM Framework",
        "id": "artifact-current",
    } in task_result["data"]["destinations"]

    next_steps = reply.blocks[-1]["data"]["items"]
    actions = {item["action"]: item for item in next_steps}

    assert actions["open_artifact"]["params"] == {
        "artifact_id": "artifact-current"
    }

    rerun_params = actions["rerun_from_artifact"]["params"]
    assert rerun_params["topic"] == "LLM planning"
    assert rerun_params["source_artifact_id"] == "artifact-current"
    assert rerun_params["context_artifact_ids"] == ["artifact-current"]
    assert "__internal_trace" not in rerun_params


def test_prism_completion_card_keeps_artifact_action_after_review_actions() -> None:
    reply = build_feature_task_completion_card(
        feature_id="writing",
        task_id="task-prism-artifact",
        execution_session_id="exec-prism-artifact",
        payload={"params": {"paper_title": "Agent Paper"}},
        result={
            "data": {
                "latex_project_id": "project-1",
                "pending_file_changes": 1,
                "compile_status": "blocked_by_review",
                "prism_url": "/latex/project-1",
            },
            "artifacts": [{"id": "artifact-draft", "title": "Introduction draft"}],
        },
    )

    next_steps = reply.blocks[-1]["data"]["items"]
    assert [item["action"] for item in next_steps[:3]] == [
        "preview_prism_changes",
        "open_prism",
        "open_artifact",
    ]
    assert next_steps[2]["params"]["artifact_id"] == "artifact-draft"


def test_activity_retry_resolves_against_the_task_result_artifact() -> None:
    activity = build_task_activity_item(
        task_id="task-artifact",
        workspace_id="ws-1",
        task_type="workspace_feature",
        payload={
            "feature_id": "framework_outline",
            "thread_id": "thread-1",
            "params": {"topic": "LLM planning"},
        },
        status="success",
        progress=100,
        message="done",
        error=None,
        result={"artifact_ids": ["artifact-current"]},
        occurred_at="2026-03-25T00:00:00Z",
        completed_at="2026-03-25T00:00:00Z",
    )
    workspace = Workspace(
        id="ws-1",
        user_id="user-1",
        name="Agent Workspace",
        type=WorkspaceType.SCI,
        discipline="computer_science",
        description="Research on agent planning and execution",
        config={},
    )
    older = Artifact(
        id="artifact-older",
        workspace_id="ws-1",
        type="paper_analysis",
        title="Older Artifact",
        content={"topic": "older"},
    )
    current = Artifact(
        id="artifact-current",
        workspace_id="ws-1",
        type="paper_analysis",
        title="Current Artifact",
        content={"topic": "current"},
    )

    state = resolve_feature_action_state(
        feature_id="framework_outline",
        workspace=workspace,
        artifacts=[older, current],
        orchestration_params=activity["metadata"]["params"],
        follow_up_prompt="继续深化框架",
    )

    assert activity["artifact_id"] == "artifact-current"
    assert state["source_artifact_id"] == "artifact-current"
    assert state["route_params"]["source_artifact_id"] == "artifact-current"
    assert state["rerun_params"]["context_artifact_ids"] == ["artifact-current"]
