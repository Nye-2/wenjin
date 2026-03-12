"""Custom task handlers for unified workspace feature execution."""

import logging
from typing import Any

from src.task.progress import ProgressTracker
from src.thesis.workflow.runner import run_thesis_workflow_request
from src.workspace_features import execute_registered_feature, get_workspace_feature

logger = logging.getLogger(__name__)

THESIS_WORKSPACE_TYPES: set[str] = set()  # 不再按 workspace_type 判断
THESIS_AGENTS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 agent 检测
THESIS_HANDLER_KEYS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 handler_key 检测


def _is_thesis_payload(payload: dict[str, Any]) -> bool:
    """Determine whether a task payload should run the thesis workflow."""
    workspace_type = payload.get("workspace_type")
    agent = payload.get("agent")
    handler_key = payload.get("handler_key")
    return (
        workspace_type in THESIS_WORKSPACE_TYPES
        or agent in THESIS_AGENTS
        or handler_key in THESIS_HANDLER_KEYS
    )


def _normalize_progress(progress: float | int | None) -> int:
    """Convert workflow progress to an integer percentage."""
    if progress is None:
        return 0
    numeric = float(progress)
    if numeric <= 1:
        numeric *= 100
    return max(0, min(int(round(numeric)), 100))


def _build_thesis_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a unified task payload to the thesis workflow request shape."""
    return {
        "workspace_id": payload.get("workspace_id", ""),
        "thread_id": payload.get("thread_id")
        or payload.get("task_id")
        or payload.get("workspace_id", ""),
        "paper_title": payload.get("paper_title")
        or payload.get("title")
        or payload.get("feature_name")
        or "未命名论文",
        "discipline": payload.get("discipline", "计算机科学"),
        "abstract_content": payload.get("abstract_content") or payload.get("abstract", ""),
        "framework_json": payload.get("framework_json") or payload.get("framework", {}),
        "enable_search": payload.get("enable_search", True),
        "enable_images": payload.get("enable_images", payload.get("feature_id") == "figure"),
    }


async def execute_thesis_generation(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute thesis generation on the unified task infrastructure."""
    request = _build_thesis_request(payload)

    async def on_update(update: dict[str, Any]) -> None:
        metadata = {
            "feature_id": payload.get("feature_id"),
            "feature_name": payload.get("feature_name"),
            "workspace_type": payload.get("workspace_type", "thesis"),
            "handler_key": payload.get("handler_key"),
            "current_phase": update.get("current_phase"),
            "sections_completed": update.get("sections_completed", 0),
            "sections_total": update.get("sections_total", 0),
            "latex_content": update.get("latex_content", ""),
            "bib_content": update.get("bib_content", ""),
            "pdf_path": update.get("pdf_path", ""),
        }
        await progress.update(
            _normalize_progress(update.get("progress")),
            update.get("message"),
            current_step=update.get("current_phase"),
            metadata=metadata,
        )

    result = await run_thesis_workflow_request(request, on_update=on_update)
    return {
        "feature_id": payload.get("feature_id"),
        "feature_name": payload.get("feature_name"),
        "workspace_type": payload.get("workspace_type", "thesis"),
        "handler_key": payload.get("handler_key"),
        **result,
    }


async def execute_workspace_feature(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute a workspace feature using the registry-defined handler key."""
    if _is_thesis_payload(payload):
        return await execute_thesis_generation(payload, progress)

    workspace_type = str(payload.get("workspace_type") or "")
    feature_id = str(payload.get("feature_id") or "")
    feature = get_workspace_feature(workspace_type, feature_id)
    if not feature:
        raise ValueError(
            f"Unknown workspace feature '{feature_id}' for workspace type '{workspace_type}'"
        )

    return await execute_registered_feature(payload, progress, feature)
