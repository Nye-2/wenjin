"""Runtime checks for workspace feature action-state rules.

Previously these tests ran the frontend resolver via tsx. After backend-
migration of the resolver logic (SSOT convergence Phase 3), action-state
cases now test the backend ``resolve_feature_action_state`` directly.
Other frontend runtime checks (skill sync, markdown export) still run
via tsx against the unchanged frontend modules.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.database.models.artifact import Artifact
from src.database.models.workspace import Workspace, WorkspaceType
from src.services.feature_action_resolution_service import resolve_feature_action_state

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
TSX_PACKAGE = FRONTEND_DIR / "node_modules" / "tsx"


def _workspace(*, workspace_type: str) -> Workspace:
    return Workspace(
        id="ws-1",
        user_id="user-1",
        name="Agent Workspace",
        type=WorkspaceType(workspace_type),
        discipline="computer_science",
        description="Research on agent planning and execution",
        config={},
    )


def _artifact(
    *,
    artifact_type: str,
    title: str | None = None,
    content: dict[str, object] | None = None,
) -> Artifact:
    return Artifact(
        id="art-1",
        workspace_id="ws-1",
        type=artifact_type,
        title=title,
        content=content or {},
    )


def _resolve_action_state(
    feature_id: str,
    workspace: Workspace | None,
    artifacts: list[Artifact],
    orchestration_params: dict[str, object] | None = None,
    explicit_source_artifact_id: str | None = None,
) -> dict[str, object]:
    state = resolve_feature_action_state(
        feature_id=feature_id,
        workspace=workspace,
        artifacts=artifacts,
        orchestration_params=orchestration_params,
        explicit_source_artifact_id=explicit_source_artifact_id,
        follow_up_prompt="",
    )
    # Map backend snake_case to frontend camelCase for test compatibility
    return {
        "sourceArtifact": None,
        "followUpPrompt": state["follow_up_prompt"],
        "routeParams": state["route_params"],
        "rerunParams": state.get("rerun_params"),
        "rerunUnavailableReason": state.get("rerun_unavailable_reason"),
    }


def _sync_chat_skill_state(payload: dict[str, object]) -> dict[str, object]:
    assert TSX_PACKAGE.exists(), "tsx package is required for frontend runtime tests"
    code = (
        'const __skillState = await import("./lib/thread-skill-state.ts");'
        "const { syncCurrentSkillWithThread } = __skillState.default ?? __skillState;"
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "console.log(JSON.stringify(syncCurrentSkillWithThread(input)));"
    )
    completed = subprocess.run(
        ["node", "--import", "tsx", "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _format_conversation_markdown(payload: dict[str, object]) -> str:
    assert TSX_PACKAGE.exists(), "tsx package is required for frontend runtime tests"
    code = (
        'const __threadExport = await import("./lib/thread-export.ts");'
        "const { formatConversationAsMarkdown } = __threadExport.default ?? __threadExport;"
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "console.log(formatConversationAsMarkdown(input.thread, input.messages));"
    )
    completed = subprocess.run(
        ["node", "--import", "tsx", "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


@pytest.mark.parametrize(
    ("feature_id", "workspace_type", "params", "expected_keys"),
    [
        (
            "thesis_research_pack",
            "thesis",
            {"topic": "LLM planning"},
            {"topic", "goal"},
        ),
        (
            "sci_literature_positioning",
            "sci",
            {"query": "LLM planning", "discipline": "cs"},
            {"query", "discipline", "goal"},
        ),
        (
            "sci_empirical_package",
            "sci",
            {"reference_id": "ref-1", "paper_title": "Agent Paper"},
            {"reference_id", "paper_title", "goal"},
        ),
        (
            "research_question_to_paper",
            "sci",
            {"paper_title": "Agent Paper", "section_type": "introduction"},
            {"paper_title", "section_type", "goal"},
        ),
        (
            "sci_revision_for_journal",
            "sci",
            {"topic": "LLM planning"},
            {"topic", "goal"},
        ),
        (
            "research_question_to_paper",
            "sci",
            {"paper_title": "Agent Paper", "topic": "LLM planning"},
            {"paper_title", "topic", "goal"},
        ),
        (
            "reproducibility_audit",
            "sci",
            {"paper_title": "Agent Paper", "manuscript_excerpt": "Draft body"},
            {"paper_title", "manuscript_excerpt", "goal"},
        ),
        (
            "journal_submission_strategy",
            "sci",
            {"paper_title": "Agent Paper", "abstract": "Study of agent systems"},
            {"paper_title", "abstract", "goal"},
        ),
        (
            "idea_to_thesis_manuscript",
            "thesis",
            {"topic": "LLM planning", "report_type": "opening_report"},
            {"topic", "report_type", "goal"},
        ),
        (
            "idea_to_thesis_manuscript",
            "thesis",
            {"action": "generate_outline", "paper_title": "Agent Thesis"},
            {"action", "paper_title", "goal"},
        ),
        (
            "software_architecture_diagrams",
            "thesis",
            {"description": "A flowchart", "type": "flowchart"},
            {"description", "type", "goal"},
        ),
        (
            "technical_route_package",
            "proposal",
            {"topic": "Agent evaluation", "objective": "Design a benchmark"},
            {"topic", "objective", "goal"},
        ),
        (
            "idea_to_proposal_package",
            "proposal",
            {"topic": "Agent evaluation", "proposal_type": "NSF", "period_months": 36},
            {"topic", "proposal_type", "period_months", "goal"},
        ),
        (
            "proposal_background_pack",
            "proposal",
            {"keywords": "Agent evaluation", "industry_scope": "AI", "time_range": "近5年"},
            {"keywords", "industry_scope", "time_range", "goal"},
        ),
        (
            "invention_to_patent_draft",
            "patent",
            {"innovation_description": "Novel battery", "technical_field": "Energy"},
            {"innovation_description", "technical_field", "goal"},
        ),
        (
            "software_copyright_application_pack",
            "software_copyright",
            {"software_name": "Wenjin", "version": "V1.0"},
            {"software_name", "version", "goal"},
        ),
        (
            "software_technical_manual",
            "software_copyright",
            {"software_name": "Wenjin", "version": "V1.0", "deployment_architecture": "B/S架构"},
            {"software_name", "version", "deployment_architecture", "goal"},
        ),
    ],
)
def test_rerun_params_contain_expected_keys(
    feature_id: str,
    workspace_type: str,
    params: dict[str, object],
    expected_keys: set[str],
) -> None:
    state = _resolve_action_state(
        feature_id=feature_id,
        workspace=_workspace(workspace_type=workspace_type),
        artifacts=[],
        orchestration_params=params,
    )

    rerun_params = state["rerunParams"]
    assert isinstance(rerun_params, dict), f"Expected dict for {feature_id}, got {rerun_params!r}"
    assert expected_keys.issubset(set(rerun_params)), (
        f"Missing keys for {feature_id}: {expected_keys - set(rerun_params)}"
    )
    assert state["rerunUnavailableReason"] is None


def test_unknown_feature_id_returns_fallback() -> None:
    state = _resolve_action_state(
        feature_id="unknown_feature",
        workspace=_workspace(workspace_type="sci"),
        artifacts=[],
        orchestration_params={"topic": "test"},
    )
    assert state["rerunParams"] is None
    assert state["rerunUnavailableReason"] is not None


def test_null_workspace_without_goal_is_not_rerunnable() -> None:
    state = _resolve_action_state(
        feature_id="thesis_research_pack",
        workspace=None,
        artifacts=[],
        orchestration_params=None,
    )
    assert state["rerunParams"] is None
    assert state["rerunUnavailableReason"] == "缺少可复用的 mission goal 或来源材料。"


def test_null_orchestration_params_without_source_is_not_rerunnable() -> None:
    state = _resolve_action_state(
        feature_id="thesis_research_pack",
        workspace=_workspace(workspace_type="thesis"),
        artifacts=[],
        orchestration_params=None,
    )
    assert state["rerunParams"] is None
    assert state["rerunUnavailableReason"] == "缺少可复用的 mission goal 或来源材料。"


def test_explicit_source_artifact_id_takes_precedence() -> None:
    artifacts = [
        _artifact(artifact_type="paper_analysis", title="Older", content={"topic": "old"}),
        _artifact(artifact_type="paper_analysis", title="Explicit", content={"topic": "explicit"}),
    ]
    state = _resolve_action_state(
        feature_id="sci_empirical_package",
        workspace=_workspace(workspace_type="sci"),
        artifacts=artifacts,
        orchestration_params=None,
        explicit_source_artifact_id=str(artifacts[1].id),
    )
    route_params = state["routeParams"]
    assert route_params.get("source_artifact_id") == str(artifacts[1].id)


def test_implicit_source_artifact_picks_latest_by_created_at() -> None:
    from datetime import UTC, datetime

    older = _artifact(artifact_type="paper_analysis", title="Older")
    older.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    newer = _artifact(artifact_type="paper_analysis", title="Newer")
    newer.created_at = datetime(2024, 6, 1, tzinfo=UTC)

    state = _resolve_action_state(
        feature_id="sci_empirical_package",
        workspace=_workspace(workspace_type="sci"),
        artifacts=[older, newer],
        orchestration_params=None,
    )
    route_params = state["routeParams"]
    assert route_params.get("source_artifact_id") == str(newer.id)


def test_source_artifact_id_not_leaked_into_rerun_params() -> None:
    state = _resolve_action_state(
        feature_id="research_question_to_paper",
        workspace=_workspace(workspace_type="sci"),
        artifacts=[_artifact(artifact_type="paper_draft", title="Draft")],
        orchestration_params={"paper_title": "Test"},
    )
    rerun_params = state["rerunParams"]
    assert "source_artifact_id" not in rerun_params


def test_thread_skill_sync_preserves_pending_local_selection_until_server_catches_up() -> None:
    state = _sync_chat_skill_state(
        {
            "currentSkill": "peer-reviewer",
            "nextThreadSkill": "deep-research",
            "isSkillSelectionPending": True,
        }
    )

    assert state == {
        "currentSkill": "peer-reviewer",
        "threadSkill": "deep-research",
        "activeSkill": "peer-reviewer",
        "isSkillSelectionPending": True,
    }


def test_thread_skill_sync_clears_pending_flag_after_server_matches_selection() -> None:
    state = _sync_chat_skill_state(
        {
            "currentSkill": "peer-reviewer",
            "nextThreadSkill": "peer-reviewer",
            "isSkillSelectionPending": True,
        }
    )

    assert state == {
        "currentSkill": None,
        "threadSkill": "peer-reviewer",
        "activeSkill": "peer-reviewer",
        "isSkillSelectionPending": False,
    }


def test_thread_skill_sync_uses_server_skill_when_no_local_pending_selection() -> None:
    state = _sync_chat_skill_state(
        {
            "currentSkill": "peer-reviewer",
            "nextThreadSkill": None,
            "isSkillSelectionPending": False,
        }
    )

    assert state == {
        "currentSkill": None,
        "threadSkill": None,
        "activeSkill": None,
        "isSkillSelectionPending": False,
    }


def test_markdown_export_uses_backend_skill_name_for_human_readable_output() -> None:
    markdown = _format_conversation_markdown(
        {
            "thread": {
                "id": "thread-1",
                "workspace_id": "ws-1",
                "model": "gpt-4.1",
                "skill": "peer-reviewer",
                "skill_name": "Peer Review",
            },
            "messages": [],
        }
    )

    assert "# Peer Review" in markdown
    assert "- Skill: Peer Review" in markdown
