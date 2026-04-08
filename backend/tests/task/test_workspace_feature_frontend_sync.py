"""Consistency checks for workspace feature registry and frontend mappings."""

from __future__ import annotations

import re
from pathlib import Path

from src.workspace_features import CANONICAL_WORKSPACE_TYPES, list_workspace_features

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
ROUTES_FILE = FRONTEND_DIR / "lib" / "workspace-feature-routes.ts"
ACTIONS_FILE = FRONTEND_DIR / "lib" / "workspace-feature-actions.ts"
EXECUTION_FILE = FRONTEND_DIR / "lib" / "workspace-feature-execution.ts"
FEATURE_RUNNER_FILE = FRONTEND_DIR / "hooks" / "useFeatureTaskRunner.ts"
CHAT_EXPORT_FILE = FRONTEND_DIR / "lib" / "chat-export.ts"
WORKSPACE_API_FILE = FRONTEND_DIR / "lib" / "api" / "workspace.ts"
CHAT_ROUTE_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "chat" / "page.tsx"
)
CHAT_ENTRY_FILE = FRONTEND_DIR / "lib" / "workspace-chat-entry.ts"
CHAT_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "ChatPanel.tsx"
)
AGENT_STATUS_BAR_FILE = FRONTEND_DIR / "components" / "workspace" / "AgentStatusBar.tsx"
KNOWLEDGE_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "KnowledgePanel.tsx"
)
WORKBENCH_LAYOUT_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "layout.tsx"
)
WORKSPACE_STORE_FILE = FRONTEND_DIR / "stores" / "workspace.ts"
WORKSPACE_EVENT_STREAM_FILE = FRONTEND_DIR / "hooks" / "useWorkspaceEventStream.ts"
WORKSPACE_PAGES_DIR = FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]"


def _registry_feature_ids() -> set[str]:
    return {
        feature.id
        for workspace_type in CANONICAL_WORKSPACE_TYPES
        for feature in list_workspace_features(workspace_type)
    }


def _followup_prompt_reads_from_api() -> bool:
    """Return True if getFeatureFollowUpPrompt reads followUpPrompt from a feature object (API-driven)."""
    content = ACTIONS_FILE.read_text(encoding="utf-8")
    return bool(
        re.search(
            r"export function getFeatureFollowUpPrompt\(",
            content,
        )
        and re.search(r"followUpPrompt", content)
    )


def _extract_action_case_keys() -> set[str]:
    content = ACTIONS_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'case "([a-z_]+)"\s*:', content))


def _extract_retry_feature_task_body() -> str:
    content = KNOWLEDGE_PANEL_FILE.read_text(encoding="utf-8")
    block = re.search(
        r"const retryFeatureTask = async\s*\(.*?\)\s*=>\s*\{(?P<body>.*?)\n  \};",
        content,
        flags=re.DOTALL,
    )
    assert block is not None, "retryFeatureTask not found in KnowledgePanel"
    return block.group("body")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_case_body(path: Path, case_name: str) -> str:
    content = _read_text(path)
    block = re.search(
        rf'case "{re.escape(case_name)}":(?P<body>.*?)(?=\n    case |\n    default:)',
        content,
        flags=re.DOTALL,
    )
    assert block is not None, f"{case_name} case not found in {path.name}"
    return block.group("body")


def test_workspace_feature_routes_match_backend_registry() -> None:
    content = _read_text(ROUTES_FILE)
    for feature_id in _registry_feature_ids():
        assert f'query.set("feature", featureId);' in content
        assert "return getWorkspaceFeatureChatRoute(workspaceId, featureId, params);" in content


def test_workspace_feature_routes_use_canonical_chat_entry() -> None:
    content = _read_text(ROUTES_FILE)
    assert 'const pathname = `/workspaces/${workspaceId}/chat`;' in content
    assert 'query.set("feature", featureId);' in content
    assert "query.append(key, value);" in content


def test_chat_route_consumes_feature_entry_seed_and_ensures_workspace_main_thread() -> None:
    chat_route_body = _read_text(CHAT_ROUTE_FILE)
    chat_entry_body = _read_text(CHAT_ENTRY_FILE)
    chat_panel_body = _read_text(CHAT_PANEL_FILE)
    layout_body = _read_text(WORKBENCH_LAYOUT_FILE)

    assert "parseWorkspaceChatEntrySeed(searchParams)" in chat_route_body
    assert "<ChatPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />" in chat_route_body
    assert "export function parseWorkspaceChatEntrySeed(" in chat_entry_body
    assert "export function buildWorkspaceChatEntryPrompt(" in chat_entry_body
    assert 'feature_id: entrySeed.featureId' in chat_panel_body
    assert "params: entrySeed.params" in chat_panel_body
    assert "void loadThreads(workspaceId);" not in layout_body
    assert "ensureWorkspaceThread(workspaceId" in chat_route_body


def test_workspace_feature_actions_explicitly_cover_all_features() -> None:
    registry_feature_ids = _registry_feature_ids()
    action_case_keys = _extract_action_case_keys()

    # Follow-up prompts live in the backend registry (see test_registry_spec.py::test_every_feature_has_follow_up_prompt).
    # Verify the frontend reads them from the API rather than a hardcoded dict.
    assert _followup_prompt_reads_from_api(), (
        "getFeatureFollowUpPrompt must read followUpPrompt from the feature object (API-driven). "
        "See backend/src/workspace_features/registry.py."
    )

    missing_action_cases = sorted(registry_feature_ids - action_case_keys)
    assert not missing_action_cases, f"Missing action-state cases for: {missing_action_cases}"


def test_workspace_chat_skill_catalog_is_loaded_from_backend_api() -> None:
    chat_panel_body = _read_text(CHAT_PANEL_FILE)
    skill_selector_body = _read_text(
        FRONTEND_DIR
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "components"
        / "SkillSelector.tsx"
    )
    assert "useFeaturesStore((state) => state.skills)" in skill_selector_body
    assert "getSkillById" in chat_panel_body


def test_knowledge_panel_retry_uses_feature_action_state() -> None:
    body = _extract_retry_feature_task_body()
    assert "actionState?.rerunParams" in body
    assert "actionState.rerunParams" in body
    assert "item.metadata?.params" not in body


def test_chat_skill_labels_use_shared_formatter_in_human_readable_surfaces() -> None:
    for path in (
        CHAT_EXPORT_FILE,
        CHAT_PANEL_FILE,
        KNOWLEDGE_PANEL_FILE,
        AGENT_STATUS_BAR_FILE,
    ):
        body = _read_text(path)
        assert "getSkillById" in body or "skillLabel" in body or "thread.skill" in body


def test_chat_and_knowledge_submission_flow_use_shared_execution_helper() -> None:
    execution_body = _read_text(EXECUTION_FILE)
    chat_body = _read_text(CHAT_PANEL_FILE)
    knowledge_body = _read_text(KNOWLEDGE_PANEL_FILE)
    feature_runner_body = _read_text(FEATURE_RUNNER_FILE)

    assert "export async function createWorkspaceFeatureTask(" in execution_body
    assert "export function ensureWorkspaceFeatureTaskCreated(" in execution_body
    assert "executeWorkspaceFeature(" in execution_body

    assert "createWorkspaceFeatureTask({" in chat_body
    assert "executeWorkspaceFeature(" not in chat_body

    assert "createWorkspaceFeatureTask({" in knowledge_body
    assert "executeWorkspaceFeature(" not in knowledge_body

    assert "ensureWorkspaceFeatureTaskCreated(resp" in feature_runner_body


def test_agent_status_bar_uses_backend_cancel_api_and_failed_task_branch() -> None:
    api_body = _read_text(WORKSPACE_API_FILE)
    body = _read_text(AGENT_STATUS_BAR_FILE)

    assert "export async function cancelTask(taskId: string): Promise<void>" in api_body
    assert 'await apiClient.delete(`/tasks/${taskId}`);' in api_body

    assert 'currentTask?.status === "failed"' in body
    assert "await cancelTaskRequest(currentTask.id);" in body


def test_workspace_event_stream_applies_thread_activity_incrementally() -> None:
    store_body = _read_text(WORKSPACE_STORE_FILE)
    task_updated_body = _extract_case_body(WORKSPACE_EVENT_STREAM_FILE, "task.updated")
    updated_body = _extract_case_body(WORKSPACE_EVENT_STREAM_FILE, "thread.updated")
    deleted_body = _extract_case_body(WORKSPACE_EVENT_STREAM_FILE, "thread.deleted")
    subagent_updated_body = _extract_case_body(WORKSPACE_EVENT_STREAM_FILE, "subagent.updated")

    assert "upsertActivity: (activity: WorkspaceActivityItem) => void;" in store_body
    assert "removeActivity: (activityId: string) => void;" in store_body

    assert "workspaceStore.upsertActivity(event.activity);" in task_updated_body

    assert "workspaceStore.upsertActivity(event.activity);" in updated_body
    assert 'refreshWorkspaceTargets(workspaceId, ["activity"]);' in updated_body
    assert "chatStore.refreshCurrentThread(workspaceId" in updated_body

    assert "workspaceStore.removeActivity(event.activity_id);" in deleted_body
    assert 'refreshWorkspaceTargets(workspaceId, ["activity"]);' in deleted_body

    assert "workspaceStore.upsertActivity(event.activity);" in subagent_updated_body
    assert 'refreshWorkspaceTargets(workspaceId, ["activity"]);' in subagent_updated_body


def test_knowledge_panel_uses_canonical_subagent_title_instead_of_raw_type_formatting() -> None:
    body = _read_text(KNOWLEDGE_PANEL_FILE)
    assert "selectedActivity.title || \"未指定\"" in body
    assert "item.title || \"子代理任务\"" in body
    assert "selectedActivity.subagent_type.replace" not in body
    assert "item.subagent_type.replace" not in body
