"""Runtime checks for frontend workspace feature action-state rules."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
TSX_BIN = FRONTEND_DIR / "node_modules" / ".bin" / "tsx"


def _workspace(*, workspace_type: str) -> dict[str, object]:
    return {
        "id": "ws-1",
        "user_id": "user-1",
        "name": "Agent Workspace",
        "type": workspace_type,
        "discipline": "computer_science",
        "description": "Research on agent planning and execution",
        "config": {},
        "created_at": "2026-03-25T00:00:00Z",
        "updated_at": "2026-03-25T00:00:00Z",
    }


def _resolve_action_state(payload: dict[str, object]) -> dict[str, object]:
    assert TSX_BIN.exists(), "tsx binary is required for frontend action-state runtime tests"
    code = (
        'import { resolveFeatureActionState } from "./lib/workspace-feature-actions.ts";'
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "const result = resolveFeatureActionState(input);"
        "console.log(JSON.stringify(result));"
    )
    completed = subprocess.run(
        [str(TSX_BIN), "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _resolve_warning_message(payload: dict[str, object]) -> str:
    assert TSX_BIN.exists(), "tsx binary is required for frontend runtime tests"
    code = (
        'import { getWorkspaceFeatureExecutionWarningMessage } from "./lib/workspace-feature-execution.ts";'
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        'console.log(getWorkspaceFeatureExecutionWarningMessage(input, "fallback"));'
    )
    completed = subprocess.run(
        [str(TSX_BIN), "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sync_chat_skill_state(payload: dict[str, object]) -> dict[str, object]:
    assert TSX_BIN.exists(), "tsx binary is required for frontend runtime tests"
    code = (
        'import { syncCurrentSkillWithThread } from "./lib/chat-skill-state.ts";'
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "console.log(JSON.stringify(syncCurrentSkillWithThread(input)));"
    )
    completed = subprocess.run(
        [str(TSX_BIN), "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _format_conversation_markdown(payload: dict[str, object]) -> str:
    assert TSX_BIN.exists(), "tsx binary is required for frontend runtime tests"
    code = (
        'import { formatConversationAsMarkdown } from "./lib/chat-export.ts";'
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "console.log(formatConversationAsMarkdown(input.thread, input.messages));"
    )
    completed = subprocess.run(
        [str(TSX_BIN), "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _ensure_task_created(payload: dict[str, object]) -> dict[str, object]:
    assert TSX_BIN.exists(), "tsx binary is required for frontend runtime tests"
    code = (
        'import { ensureWorkspaceFeatureTaskCreated } from "./lib/workspace-feature-execution.ts";'
        f"const input = {json.dumps(payload, ensure_ascii=False)};"
        "try {"
        '  const result = ensureWorkspaceFeatureTaskCreated(input.execution, input.fallbacks);'
        '  console.log(JSON.stringify({ ok: true, result }));'
        "} catch (error) {"
        '  const message = error instanceof Error ? error.message : String(error);'
        '  console.log(JSON.stringify({ ok: false, error: message }));'
        "}"
    )
    completed = subprocess.run(
        [str(TSX_BIN), "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("feature_id", "workspace_type", "params", "expected_keys"),
    [
        (
            "literature_review",
            "sci",
            {"topic": "LLM planning"},
            {"topic", "discipline"},
        ),
        (
            "framework_outline",
            "sci",
            {"paper_title": "Agent Paper", "topic": "LLM planning"},
            {"paper_title", "topic"},
        ),
        (
            "peer_review",
            "sci",
            {"paper_title": "Agent Paper", "manuscript_excerpt": "Draft body"},
            {"paper_title", "manuscript_excerpt"},
        ),
        (
            "journal_recommend",
            "sci",
            {"paper_title": "Agent Paper", "abstract": "Study of agent systems"},
            {"paper_title", "abstract", "discipline"},
        ),
        (
            "experiment_design",
            "proposal",
            {"topic": "Agent evaluation", "objective": "Design a benchmark"},
            {"topic", "objective"},
        ),
    ],
)
def test_text_based_rerun_params_do_not_require_local_source_artifact(
    feature_id: str,
    workspace_type: str,
    params: dict[str, object],
    expected_keys: set[str],
) -> None:
    state = _resolve_action_state(
        {
            "featureId": feature_id,
            "workspace": _workspace(workspace_type=workspace_type),
            "artifacts": [],
            "orchestrationParams": params,
        }
    )

    rerun_params = state["rerunParams"]
    assert isinstance(rerun_params, dict)
    assert expected_keys.issubset(set(rerun_params))
    assert state["rerunUnavailableReason"] is None


def test_warning_message_formats_literature_insufficient_detail() -> None:
    message = _resolve_warning_message(
        {
            "warning": "literature_insufficient",
            "message": "文献不足",
            "detail": {"current": 2, "recommended": 15},
        }
    )

    assert message == "文献数量不足（当前 2 / 推荐 15），请先在「文献管理」中补充文献。"


def test_warning_message_falls_back_to_backend_message() -> None:
    message = _resolve_warning_message(
        {
            "warning": "unknown_warning",
            "message": "该功能暂不可用",
            "detail": None,
        }
    )

    assert message == "该功能暂不可用"


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


def test_ensure_workspace_feature_task_created_returns_task_identity() -> None:
    result = _ensure_task_created(
        {
            "execution": {
                "task_id": "task-123",
                "status": "submitted",
                "feature_id": "deep_research",
                "message": "任务已提交",
            },
            "fallbacks": {
                "warningFallback": "warning",
                "missingTaskFallback": "missing",
            },
        }
    )

    assert result == {
        "ok": True,
        "result": {
            "taskId": "task-123",
            "message": "任务已提交",
            "execution": {
                "task_id": "task-123",
                "status": "submitted",
                "feature_id": "deep_research",
                "message": "任务已提交",
            },
        },
    }


def test_ensure_workspace_feature_task_created_surfaces_warning_message() -> None:
    result = _ensure_task_created(
        {
            "execution": {
                "task_id": None,
                "status": "warning",
                "feature_id": "thesis_writing",
                "message": "文献不足",
                "warning": "literature_insufficient",
                "detail": {"current": 1, "recommended": 12},
            },
            "fallbacks": {
                "warningFallback": "warning",
                "missingTaskFallback": "missing",
            },
        }
    )

    assert result == {
        "ok": False,
        "error": "文献数量不足（当前 1 / 推荐 12），请先在「文献管理」中补充文献。",
    }
