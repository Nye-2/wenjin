"""Consistency checks for workspace feature registry and frontend mappings."""

from __future__ import annotations

import re
from pathlib import Path

from src.workspace_features import CANONICAL_WORKSPACE_TYPES, list_workspace_features

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
ROUTES_FILE = FRONTEND_DIR / "lib" / "workspace-feature-routes.ts"
ACTIONS_FILE = FRONTEND_DIR / "lib" / "workspace-feature-actions.ts"
THREAD_EXPORT_FILE = FRONTEND_DIR / "lib" / "thread-export.ts"
WORKSPACE_API_FILE = FRONTEND_DIR / "lib" / "api" / "workspace.ts"
CHAT_ROUTE_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "chat" / "page.tsx"
)
CHAT_ENTRY_FILE = FRONTEND_DIR / "lib" / "workspace-thread-entry.ts"
CHAT_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "ThreadPanel.tsx"
)
WORKSPACE_INSPECTOR_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "WorkspaceInspector.tsx"
)
CHAT_STORE_FILE = FRONTEND_DIR / "stores" / "thread.ts"
CHAT_STORE_SUPPORT_FILE = FRONTEND_DIR / "stores" / "thread-store-support.ts"
COMPUTE_STAGE_FILE = FRONTEND_DIR / "components" / "compute" / "ComputeStage.tsx"
COMPUTE_PRISM_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "PrismPanel.tsx"
COMPUTE_SANDBOX_FILE_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "SandboxFilePanel.tsx"
COMPUTE_LOG_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "LogPanel.tsx"
COMPUTE_REVIEW_GATE_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "ReviewGatePanel.tsx"
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
FEATURE_RUNNER_FILE = FRONTEND_DIR / "hooks" / "useFeatureTaskRunner.ts"
QUICK_ACTIONS_FILE = FRONTEND_DIR / "components" / "workspace" / "QuickActions.tsx"
WORKSPACE_THREAD_SKILLS_FILE = FRONTEND_DIR / "lib" / "workspace-chat-skills.ts"
MODULE_CARD_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "ModuleCard.tsx"
)


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
    for _feature_id in _registry_feature_ids():
        assert 'query.set("feature", featureId);' in content
        assert "return getWorkspaceFeatureThreadRoute(workspaceId, featureId, params);" in content


def test_workspace_feature_routes_use_canonical_chat_entry() -> None:
    content = _read_text(ROUTES_FILE)
    assert 'const pathname = `/workspaces/${workspaceId}/chat`;' in content
    assert 'query.set("feature", featureId);' in content
    assert "workspaceFeatureSkillMap" not in content
    assert "resolveWorkspaceFeatureSkillId" not in content
    assert "query.append(key, value);" in content


def test_chat_route_consumes_feature_entry_seed_and_ensures_workspace_main_thread() -> None:
    chat_route_body = _read_text(CHAT_ROUTE_FILE)
    chat_entry_body = _read_text(CHAT_ENTRY_FILE)
    chat_panel_body = _read_text(CHAT_PANEL_FILE)
    layout_body = _read_text(WORKBENCH_LAYOUT_FILE)

    assert "parseWorkspaceThreadEntrySeed(searchParams)" in chat_route_body
    assert "<ThreadPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />" in chat_route_body
    assert "export function parseWorkspaceThreadEntrySeed(" in chat_entry_body
    assert "export function buildWorkspaceThreadEntryPrompt(" in chat_entry_body
    assert 'intent: "launch"' in chat_panel_body
    assert 'intent: "resume"' in chat_panel_body
    assert 'feature_id: entrySeed.featureId' in chat_panel_body
    assert "params: entrySeed.params" in chat_panel_body
    assert "buildFeatureResumeMetadata(activeExecution)" in chat_panel_body
    assert "latestAssistant.metadata" not in chat_panel_body
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


def test_workspace_thread_skill_catalog_is_loaded_from_backend_api() -> None:
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
    assert not WORKSPACE_THREAD_SKILLS_FILE.exists()


def test_knowledge_panel_retry_uses_feature_action_state() -> None:
    body = _extract_retry_feature_task_body()
    assert "actionState?.rerunParams" in body
    assert "actionState.rerunParams" in body
    assert "item.metadata?.params" not in body


def test_chat_skill_labels_use_backend_contract_or_backend_skill_catalog() -> None:
    export_body = _read_text(THREAD_EXPORT_FILE)
    chat_body = _read_text(CHAT_PANEL_FILE)
    knowledge_body = _read_text(KNOWLEDGE_PANEL_FILE)
    agent_status_bar_body = _read_text(AGENT_STATUS_BAR_FILE)

    assert "workspace-chat-skills" not in export_body
    assert "thread.skill_name" in export_body

    assert "workspace-chat-skills" not in chat_body
    assert "currentThreadSummary.skill_name" in chat_body
    assert "currentThreadStatus.current_skill_name" in chat_body

    assert "workspace-chat-skills" not in knowledge_body
    assert "getSkillById" in knowledge_body

    assert "current_skill_name" in agent_status_bar_body


def test_chat_and_knowledge_panels_follow_canonical_chat_entry_and_retry_paths() -> None:
    chat_body = _read_text(CHAT_PANEL_FILE)
    chat_store_support_body = _read_text(CHAT_STORE_SUPPORT_FILE)
    knowledge_body = _read_text(KNOWLEDGE_PANEL_FILE)

    assert "buildWorkspaceThreadEntryPrompt({" in chat_body
    assert "sendMessage(prompt, {" in chat_body
    assert "createWorkspaceFeatureTask({" not in chat_body

    assert "maybeHydrateStructuredExecution" not in chat_store_support_body
    assert "useExecutionStore" not in chat_store_support_body
    assert "useTaskStore" not in chat_store_support_body

    assert "const retryFeatureTask = async" in knowledge_body
    assert "router.push(actionState.route);" in knowledge_body
    assert "createWorkspaceFeatureTask({" not in knowledge_body


def test_compute_stage_replaces_legacy_feature_panel_host() -> None:
    inspector_body = _read_text(WORKSPACE_INSPECTOR_FILE)
    compute_body = _read_text(COMPUTE_STAGE_FILE)
    prism_body = _read_text(COMPUTE_PRISM_PANEL_FILE)
    sandbox_body = _read_text(COMPUTE_SANDBOX_FILE_PANEL_FILE)
    log_body = _read_text(COMPUTE_LOG_PANEL_FILE)
    review_gate_body = _read_text(COMPUTE_REVIEW_GATE_PANEL_FILE)
    workspace_exports = _read_text(FRONTEND_DIR / "components" / "workspace" / "index.ts")

    assert "ComputeStage" in inspector_body
    assert "FeaturePanelHost" not in inspector_body
    assert "useComputeStore" in compute_body
    assert "projection?.sandbox" in compute_body
    assert "projection?.prism" in compute_body
    assert "projection?.files" in compute_body
    assert "projection?.logs" in compute_body
    assert "previewLatexFileChange" in compute_body
    assert "applyLatexFileChange" in compute_body
    assert "discardLatexFileChange" in compute_body
    assert "revertLatexFileChange" in compute_body
    assert "PrismPanel" in compute_body
    assert "LatexFileChangeDiffPreview" in prism_body
    assert "reviewGate" in compute_body
    assert "Sandbox 文件" in sandbox_body
    assert "WenjinPrism" in prism_body
    assert "执行日志" in log_body
    assert "Review Gate" in review_gate_body
    assert "WorkspaceResultPanel" not in workspace_exports
    assert "FeatureWorkbenchShell" not in workspace_exports


def test_chat_store_scopes_pending_skill_and_thread_reuse_to_current_workspace() -> None:
    body = _read_text(CHAT_STORE_FILE)

    assert "pendingSkillWorkspaceId" in body
    assert "currentThreadSummary?.workspace_id" in body
    assert "requestedWorkspaceId === currentThreadWorkspaceId" in body
    assert "pendingSkillWorkspaceId === requestedWorkspaceId" in body


def test_legacy_feature_entry_shells_removed() -> None:
    assert not FEATURE_RUNNER_FILE.exists()
    assert not QUICK_ACTIONS_FILE.exists()
    assert not WORKSPACE_THREAD_SKILLS_FILE.exists()
    assert not MODULE_CARD_FILE.exists()
    assert not (FRONTEND_DIR / "lib" / "workspace-feature-execution.ts").exists()
    assert not (
        FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "features" / "[featureId]" / "page.tsx"
    ).exists()
    assert not (FRONTEND_DIR / "components" / "workspace" / "FeaturePanelHost.tsx").exists()
    assert not (FRONTEND_DIR / "components" / "workspace" / "FeatureWorkbenchShell.tsx").exists()
    assert not (FRONTEND_DIR / "components" / "workspace" / "ExecutionWorkflowGraph.tsx").exists()
    assert not (FRONTEND_DIR / "components" / "workspace" / "WorkspaceResultPanel.tsx").exists()
    assert not (FRONTEND_DIR / "lib" / "workspace-result.ts").exists()


def test_agent_status_bar_uses_backend_cancel_api_and_failed_task_branch() -> None:
    api_body = _read_text(WORKSPACE_API_FILE)
    body = _read_text(AGENT_STATUS_BAR_FILE)

    assert "export async function cancelTask(taskId: string): Promise<void>" in api_body
    assert 'await apiClient.delete(`/tasks/${taskId}`);' in api_body

    assert 'effectiveCurrentTask?.status === "failed"' in body
    assert "await cancelTaskRequest(effectiveCurrentTask.id);" in body


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
    assert "options?.scheduleThreadRefresh?.(event);" in updated_body

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
