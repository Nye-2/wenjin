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
CHAT_COMPONENTS_DIR = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components"
)
CHAT_THREAD_DIR = CHAT_COMPONENTS_DIR / "chat-thread"
MESSAGE_LIST_FILE = CHAT_THREAD_DIR / "MessageList.tsx"
QUESTION_CARD_BLOCK_FILE = CHAT_THREAD_DIR / "blocks" / "QuestionCardBlock.tsx"
RESULT_CARD_BLOCK_FILE = CHAT_THREAD_DIR / "blocks" / "ResultCardBlock.tsx"
STATUS_LINE_BLOCK_FILE = CHAT_THREAD_DIR / "blocks" / "StatusLineBlock.tsx"
AGENT_BLOCKS_FILE = FRONTEND_DIR / "lib" / "api" / "blocks.ts"
IMPORT_REFERENCES_BUTTON_FILE = FRONTEND_DIR / "components" / "workspace" / "ImportReferencesButton.tsx"
LIVE_WORKFLOW_PANEL_FILE = CHAT_COMPONENTS_DIR / "live-workflow" / "LiveWorkflowPanel.tsx"
WORKFLOW_STORE_FILE = FRONTEND_DIR / "stores" / "workflow-store.ts"
RUNS_API_FILE = FRONTEND_DIR / "lib" / "api" / "runs.ts"
WORKSPACE_ACTIVITY_DETAIL_DIALOG_FILE = (
    CHAT_COMPONENTS_DIR / "WorkspaceActivityDetailDialog.tsx"
)
WORKSPACE_ACTIVITY_DETAIL_SECTIONS_FILE = (
    CHAT_COMPONENTS_DIR / "WorkspaceActivityDetailSections.tsx"
)
APP_SHELL_SIDEBAR_FILE = FRONTEND_DIR / "components" / "workspace" / "AppShellSidebar.tsx"
CHAT_STORE_FILE = FRONTEND_DIR / "stores" / "thread.ts"
CHAT_STORE_SUPPORT_FILE = FRONTEND_DIR / "stores" / "thread-store-support.ts"
COMPUTE_STAGE_FILE = FRONTEND_DIR / "components" / "compute" / "ComputeStage.tsx"
COMPUTE_PRISM_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "PrismPanel.tsx"
COMPUTE_SANDBOX_FILE_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "SandboxFilePanel.tsx"
COMPUTE_LOG_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "LogPanel.tsx"
COMPUTE_REVIEW_GATE_PANEL_FILE = FRONTEND_DIR / "components" / "compute" / "ReviewGatePanel.tsx"
KNOWLEDGE_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "KnowledgePanel.tsx"
)
WORKBENCH_LAYOUT_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "layout.tsx"
)
WORKSPACE_STORE_FILE = FRONTEND_DIR / "stores" / "workspace.ts"
WORKSPACE_EVENT_STREAM_FILE = FRONTEND_DIR / "hooks" / "useWorkspaceEventStream.ts"
WORKSPACE_PAGES_DIR = FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]"
WORKBENCH_PAGE_FILE = WORKSPACE_PAGES_DIR / "page.tsx"
FEATURE_RUNNER_FILE = FRONTEND_DIR / "hooks" / "useFeatureTaskRunner.ts"
QUICK_ACTIONS_FILE = FRONTEND_DIR / "components" / "workspace" / "QuickActions.tsx"
WORKSPACE_THREAD_SKILLS_FILE = FRONTEND_DIR / "lib" / "workspace-chat-skills.ts"
MODULE_CARD_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "ModuleCard.tsx"
)
KNOWLEDGE_RAIL_FILE = FRONTEND_DIR / "components" / "knowledge" / "KnowledgeRail.tsx"


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


def _extract_backend_resolver_keys() -> set[str]:
    from src.services import feature_action_resolution_service
    return set(feature_action_resolution_service._RESOLVERS.keys())


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
    layout_body = _read_text(WORKBENCH_LAYOUT_FILE)

    assert "parseWorkspaceThreadEntrySeed(searchParams)" in chat_route_body
    assert "<ChatThread" in chat_route_body
    assert "<LiveWorkflowPanel workspaceId={workspaceId} />" in chat_route_body
    assert "export function parseWorkspaceThreadEntrySeed(" in chat_entry_body
    assert "export function buildWorkspaceThreadEntryPrompt(" in chat_entry_body
    # The chat-bypass removal eliminated metadata.orchestration on chat turns.
    # The chat page must NOT send orchestration; lead_agent decides launch via
    # the launch_feature tool based on the seed prompt + skill.
    assert "metadata: {" not in chat_route_body
    assert "buildWorkspaceThreadEntryOrchestration" not in chat_route_body
    assert "buildWorkspaceThreadEntryOrchestration" not in chat_entry_body
    assert "latestAssistant.metadata" not in chat_route_body
    assert "void loadThreads(workspaceId);" not in layout_body
    assert "ensureWorkspaceThread(workspaceId" in chat_route_body


def test_workspace_feature_actions_explicitly_cover_all_features() -> None:
    registry_feature_ids = _registry_feature_ids()
    resolver_keys = _extract_backend_resolver_keys()

    # Follow-up prompts live in the backend registry (see test_registry_spec.py::test_every_feature_has_follow_up_prompt).
    # Verify the frontend reads them from the API rather than a hardcoded dict.
    assert _followup_prompt_reads_from_api(), (
        "getFeatureFollowUpPrompt must read followUpPrompt from the feature object (API-driven). "
        "See backend/src/workspace_features/registry.py."
    )

    missing_resolvers = sorted(registry_feature_ids - resolver_keys)
    assert not missing_resolvers, f"Missing backend action-state resolvers for: {missing_resolvers}"


def test_workspace_thread_skill_catalog_is_loaded_from_backend_api() -> None:
    chat_route_body = _read_text(CHAT_ROUTE_FILE)
    knowledge_body = _read_text(KNOWLEDGE_PANEL_FILE)
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
    assert "resolveWorkspaceThreadEntrySkill({ seed: entrySeed, skills })" in chat_route_body
    assert "getSkillById" in knowledge_body
    assert not WORKSPACE_THREAD_SKILLS_FILE.exists()


def test_knowledge_panel_retry_uses_feature_action_state() -> None:
    body = _extract_retry_feature_task_body()
    assert "actionState?.rerunParams" in body
    assert "actionState.rerunParams" in body
    assert "item.metadata?.params" not in body


def test_chat_skill_labels_use_backend_contract_or_backend_skill_catalog() -> None:
    export_body = _read_text(THREAD_EXPORT_FILE)
    knowledge_body = _read_text(KNOWLEDGE_PANEL_FILE)
    activity_detail_body = _read_text(WORKSPACE_ACTIVITY_DETAIL_SECTIONS_FILE)
    thread_store_body = _read_text(CHAT_STORE_FILE)

    assert "workspace-chat-skills" not in export_body
    assert "thread.skill_name" in export_body

    assert "workspace-chat-skills" not in thread_store_body
    assert "summary.skill_name" in thread_store_body
    assert "status.current_skill_name" in thread_store_body

    assert "workspace-chat-skills" not in knowledge_body
    assert "getSkillById" in knowledge_body

    assert "selectedActivity.skill_name" in activity_detail_body
    assert "created_by_skill_name" in activity_detail_body


def test_chat_and_knowledge_panels_follow_canonical_chat_entry_and_retry_paths() -> None:
    chat_body = _read_text(CHAT_ROUTE_FILE)
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


def test_agent_block_contract_is_centralized_and_rendered_by_chat_thread() -> None:
    agent_blocks_body = _read_text(AGENT_BLOCKS_FILE)
    message_list_body = _read_text(MESSAGE_LIST_FILE)
    question_body = _read_text(QUESTION_CARD_BLOCK_FILE)
    result_body = _read_text(RESULT_CARD_BLOCK_FILE)
    status_body = _read_text(STATUS_LINE_BLOCK_FILE)
    import_references_body = _read_text(IMPORT_REFERENCES_BUTTON_FILE)

    expected_kinds = {
        "text",
        "status_line",
        "question_card",
        "result_card",
    }
    for kind in expected_kinds:
        assert f'"{kind}"' in agent_blocks_body

    assert "export type AgentBlock" in agent_blocks_body
    assert "isText(b)" in message_list_body
    assert "isStatusLine(b)" in message_list_body
    assert "isQuestionCard(b)" in message_list_body
    assert "isResultCard(b)" in message_list_body
    assert "<QuestionCardBlock" in message_list_body
    assert "<ResultCardBlock" in message_list_body
    assert "<StatusLineBlock" in message_list_body
    assert "onPillClick" in question_body
    assert "onFeedback" in result_body
    assert "onJumpToPhase" in status_body
    assert "await importDeepSearchArtifactReferences(workspaceId" in import_references_body


def test_chat_page_does_not_send_orchestration_metadata() -> None:
    """After chat-bypass removal, chat turns must not send metadata.orchestration."""
    chat_route_body = _read_text(CHAT_ROUTE_FILE)
    assert "buildWorkspaceThreadEntryOrchestration" not in chat_route_body
    assert "metadata: {" not in chat_route_body


def test_upload_preprocess_status_stays_visible_until_full_text_is_ready() -> None:
    store_support_body = _read_text(CHAT_STORE_SUPPORT_FILE)
    composer_body = _read_text(CHAT_COMPONENTS_DIR / "WorkspaceThreadComposer.tsx")
    literature_body = _read_text(CHAT_COMPONENTS_DIR / "LiteraturePanel.tsx")

    assert "syncAttachmentPreprocessWithTask" in store_support_body
    assert "preprocess.status = task.status" in store_support_body
    assert "pendingAttachments.map" in composer_body
    assert "uploadThreadFiles({" in _read_text(CHAT_ROUTE_FILE)
    assert 'case "running":' in literature_body
    assert "正在解析" in literature_body


def test_legacy_frontend_execute_workspace_feature_wrapper_removed() -> None:
    api_body = _read_text(WORKSPACE_API_FILE)
    type_body = _read_text(FRONTEND_DIR / "lib" / "api" / "types.ts")
    assert "executeWorkspaceFeature" not in api_body
    assert "ExecuteWorkspaceFeatureResponse" not in type_body


def test_knowledge_rail_is_connected_to_workspace_data() -> None:
    body = _read_text(KNOWLEDGE_RAIL_FILE)
    assert "TODO" not in body
    assert "useWorkspaceStore" in body
    assert "getWorkspaceMemory" in body
    assert "references.slice" in body
    assert "artifacts.slice" in body
    assert "activities.slice" in body


def test_compute_stage_replaces_legacy_feature_panel_host() -> None:
    chat_route_body = _read_text(CHAT_ROUTE_FILE)
    workbench_body = _read_text(WORKBENCH_PAGE_FILE)
    compute_body = _read_text(COMPUTE_STAGE_FILE)
    live_workflow_body = _read_text(LIVE_WORKFLOW_PANEL_FILE)
    prism_body = _read_text(COMPUTE_PRISM_PANEL_FILE)
    sandbox_body = _read_text(COMPUTE_SANDBOX_FILE_PANEL_FILE)
    log_body = _read_text(COMPUTE_LOG_PANEL_FILE)
    review_gate_body = _read_text(COMPUTE_REVIEW_GATE_PANEL_FILE)
    workspace_exports = _read_text(FRONTEND_DIR / "components" / "workspace" / "index.ts")

    assert "LiveWorkflowPanel" in chat_route_body
    assert "LiveWorkflowPanel" in workbench_body
    assert "FeaturePanelHost" not in chat_route_body
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
    assert "沙箱文件" in sandbox_body
    assert "WenjinPrism" in prism_body
    assert "执行日志" in log_body
    assert "审核关卡" in review_gate_body
    assert "WorkspaceResultPanel" not in workspace_exports
    assert "FeatureWorkbenchShell" not in workspace_exports
    assert "WorkspaceAssets" in live_workflow_body


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


def test_live_workflow_panel_uses_backend_run_lifecycle_api() -> None:
    runs_api_body = _read_text(RUNS_API_FILE)
    workflow_store_body = _read_text(WORKFLOW_STORE_FILE)
    live_panel_body = _read_text(LIVE_WORKFLOW_PANEL_FILE)
    sidebar_body = _read_text(APP_SHELL_SIDEBAR_FILE)

    assert 'postNoBody(`/api/runs/${encodeURIComponent(runId)}/pause`)' in runs_api_body
    assert 'postNoBody(`/api/runs/${encodeURIComponent(runId)}/resume`)' in runs_api_body
    assert 'fetch(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" })' in runs_api_body

    assert "pauseRunLifecycle as apiPause" in workflow_store_body
    assert "resumeRunLifecycle as apiResume" in workflow_store_body
    assert "deleteWorkspaceRun as apiDeleteRun" in workflow_store_body
    assert "pauseRun(currentRunId)" in live_panel_body
    assert "resumeRun(currentRunId)" in live_panel_body
    assert '"failed"' in sidebar_body


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


def test_workspace_refresh_artifact_target_refetches_artifact_list() -> None:
    event_stream_body = _read_text(WORKSPACE_EVENT_STREAM_FILE)
    workspace_store_body = _read_text(WORKSPACE_STORE_FILE)
    refresh_body = _extract_case_body(WORKSPACE_EVENT_STREAM_FILE, "workspace.refresh")

    assert "if (targetSet.has(\"artifacts\"))" in event_stream_body
    assert "void workspaceStore.fetchArtifacts(workspaceId);" in event_stream_body
    assert "refreshWorkspaceTargets(workspaceId, event.refresh_targets || []);" in refresh_body

    assert "fetchArtifacts: async (workspaceId: string)" in workspace_store_body
    assert "const response = await listArtifacts(workspaceId);" in workspace_store_body
    assert "artifacts: response.artifacts.map" in workspace_store_body


def test_knowledge_panel_uses_canonical_subagent_title_instead_of_raw_type_formatting() -> None:
    body = _read_text(KNOWLEDGE_PANEL_FILE)
    assert "selectedActivity.title || \"未指定\"" in body
    assert "item.title || \"子代理任务\"" in body
    assert "selectedActivity.subagent_type.replace" not in body
    assert "item.subagent_type.replace" not in body
