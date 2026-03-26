"""Consistency checks for workspace feature registry and frontend mappings."""

from __future__ import annotations

import re
from pathlib import Path

from src.agents.lead_agent.chat_skill_catalog import WORKSPACE_CHAT_SKILLS
from src.workspace_features import CANONICAL_WORKSPACE_TYPES, list_workspace_features

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
ROUTES_FILE = FRONTEND_DIR / "lib" / "workspace-feature-routes.ts"
ACTIONS_FILE = FRONTEND_DIR / "lib" / "workspace-feature-actions.ts"
CHAT_SKILLS_FILE = FRONTEND_DIR / "lib" / "workspace-chat-skills.ts"
EXECUTION_FILE = FRONTEND_DIR / "lib" / "workspace-feature-execution.ts"
FEATURE_RUNNER_FILE = FRONTEND_DIR / "hooks" / "useFeatureTaskRunner.ts"
CHAT_EXPORT_FILE = FRONTEND_DIR / "lib" / "chat-export.ts"
WORKSPACE_API_FILE = FRONTEND_DIR / "lib" / "api" / "workspace.ts"
CHAT_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "ChatPanel.tsx"
)
AGENT_STATUS_BAR_FILE = FRONTEND_DIR / "components" / "workspace" / "AgentStatusBar.tsx"
KNOWLEDGE_PANEL_FILE = (
    FRONTEND_DIR / "app" / "(workbench)" / "workspaces" / "[id]" / "components" / "KnowledgePanel.tsx"
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


def _extract_route_map() -> dict[str, str]:
    content = ROUTES_FILE.read_text(encoding="utf-8")
    block = re.search(
        r"workspaceFeatureRouteMap:\s*Record<string,\s*string>\s*=\s*\{(?P<body>.*?)\n\};",
        content,
        flags=re.DOTALL,
    )
    assert block is not None, "workspaceFeatureRouteMap not found"
    return {
        feature_id: route
        for feature_id, route in re.findall(
            r'^\s*([a-z_]+):\s*"([^"]+)",\s*$',
            block.group("body"),
            flags=re.MULTILINE,
        )
    }


def _extract_followup_prompt_keys() -> set[str]:
    content = ACTIONS_FILE.read_text(encoding="utf-8")
    block = re.search(
        r"export function getFeatureFollowUpPrompt\(featureId: string\): string \{\s*return \{(?P<body>.*?)\}\[featureId\]",
        content,
        flags=re.DOTALL,
    )
    assert block is not None, "getFeatureFollowUpPrompt mapping not found"
    return {
        key
        for key in re.findall(
            r"^\s*([a-z_]+):\s*$",
            block.group("body"),
            flags=re.MULTILINE,
        )
    }


def _extract_action_case_keys() -> set[str]:
    content = ACTIONS_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'case "([a-z_]+)"\s*:', content))


def _extract_workspace_chat_skill_catalog() -> dict[str, list[dict[str, str]]]:
    content = CHAT_SKILLS_FILE.read_text(encoding="utf-8")
    block = re.search(
        r"export const workspaceChatSkillMap.*?=\s*\{(?P<body>.*?)\}\s*as const;",
        content,
        flags=re.DOTALL,
    )
    assert block is not None, "workspaceChatSkillMap not found"

    mappings: dict[str, list[dict[str, str]]] = {}
    for section in re.finditer(
        r"^\s*([a-z_]+):\s*\[(?P<body>.*?)(?=^\s*[a-z_]+:\s*\[|\Z)",
        block.group("body"),
        flags=re.DOTALL | re.MULTILINE,
    ):
        entries: list[dict[str, str]] = []
        for entry in re.finditer(
            r'\{\s*id:\s*"(?P<id>[^"]+)",(?P<body>.*?)description:\s*"(?P<description>[^"]+)"',
            section.group("body"),
            flags=re.DOTALL,
        ):
            entries.append(
                {
                    "id": entry.group("id"),
                    "description": entry.group("description"),
                }
            )
        mappings[section.group(1)] = entries
    return mappings


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
    route_map = _extract_route_map()
    assert set(route_map) == _registry_feature_ids()


def test_workspace_feature_routes_have_pages() -> None:
    route_map = _extract_route_map()
    missing_pages = [
        feature_id
        for feature_id, route in route_map.items()
        if not (WORKSPACE_PAGES_DIR / route / "page.tsx").exists()
    ]
    assert not missing_pages, f"Missing workspace pages for: {missing_pages}"


def test_workspace_feature_actions_explicitly_cover_all_features() -> None:
    registry_feature_ids = _registry_feature_ids()
    prompt_keys = _extract_followup_prompt_keys()
    action_case_keys = _extract_action_case_keys()

    missing_prompts = sorted(registry_feature_ids - prompt_keys)
    missing_action_cases = sorted(registry_feature_ids - action_case_keys)

    assert not missing_prompts, f"Missing follow-up prompts for: {missing_prompts}"
    assert not missing_action_cases, f"Missing action-state cases for: {missing_action_cases}"


def test_workspace_chat_skill_catalog_matches_backend_bridge_mapping() -> None:
    frontend_skill_catalog = _extract_workspace_chat_skill_catalog()
    assert set(frontend_skill_catalog) == set(CANONICAL_WORKSPACE_TYPES)

    expected = {
        workspace_type: [
            {
                "id": skill.id,
                "description": skill.description,
            }
            for skill in WORKSPACE_CHAT_SKILLS.get(workspace_type, ())
        ]
        for workspace_type in CANONICAL_WORKSPACE_TYPES
    }
    assert frontend_skill_catalog == expected


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
        assert "formatWorkspaceChatSkillLabel(" in body
        assert "getWorkspaceChatSkillLabel(" not in body


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
    assert "chatStore.loadThread(event.thread.id, {" in updated_body

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
