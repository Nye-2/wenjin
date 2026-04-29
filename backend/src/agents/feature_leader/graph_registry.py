"""Feature graph registry and executor for workspace feature runtime.

This module is the feature-domain registry and executor for LangGraph
sub-graphs across all workspace types (thesis, sci, proposal, patent,
software_copyright). It is intentionally owned by FeatureLeaderRuntime, not by
the chat lead-agent.

Key features:
- Lazy loading of graph modules per workspace type
- Composite registry key: {workspace_type}.{feature_id}
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import SystemMessage

from src.workspace_features.registry import (
    WorkspaceFeatureDefinition,
    list_workspace_features,
)

logger = logging.getLogger(__name__)

__all__ = [
    "THESIS_FEATURE_IDS",
    "execute_feature_graph",
    "execute_thesis_feature_graph",
    "register_feature_graph",
]

THESIS_FEATURE_IDS = tuple(
    feature.id for feature in list_workspace_features("thesis")
)

# Type alias for feature graph functions
FeatureGraphFn = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]

# Feature graph registry: composite_key -> async callable(initial_state, payload) -> result
# Key format: "{workspace_type}.{feature_id}" (e.g., "thesis.literature_management")
_FEATURE_GRAPH_REGISTRY: dict[str, FeatureGraphFn] = {}
_LOADED_WORKSPACES: set[str] = set()
_FEATURE_MEMORY_CONTEXT_KEYS = (
    "__thread_context_focus",
    "__leader_workflow_highlights",
    "topic",
    "query",
    "keywords",
    "goal",
    "task",
    "question",
    "requirements",
    "__thread_context_digest",
)


def register_feature_graph(feature_id: str, workspace_type: str):
    """Decorator to register a feature graph function.

    Args:
        feature_id: Unique identifier for the feature (e.g., "literature_search")
        workspace_type: Workspace type for multi-workspace support
            (e.g., "sci", "patent", "thesis").

    Returns:
        Decorator function that registers the graph and returns it unchanged.
    """

    def decorator(fn: Callable) -> Callable:
        key = f"{workspace_type}.{feature_id}"
        _FEATURE_GRAPH_REGISTRY[key] = fn
        logger.debug("Registered feature graph: %s", key)
        return fn

    return decorator


def _graph_module_name(feature: WorkspaceFeatureDefinition) -> str:
    if feature.graph_module:
        return feature.graph_module
    return f"src.agents.graphs.{feature.workspace_type}.{feature.id}"


def _workspace_graph_modules(workspace_type: str) -> tuple[str, ...]:
    modules = [
        _graph_module_name(feature)
        for feature in list_workspace_features(workspace_type)
    ]
    return tuple(dict.fromkeys(modules))


def _ensure_graphs_loaded(workspace_type: str) -> None:
    """Lazy-load graph modules for a specific workspace type.

    Each workspace type's graphs are loaded independently, preventing
    errors in one workspace from affecting others.

    Args:
        workspace_type: Workspace type (thesis, sci, proposal, patent, software_copyright)
    """
    if workspace_type in _LOADED_WORKSPACES:
        return

    module_names = _workspace_graph_modules(workspace_type)
    if not module_names:
        logger.warning("Unknown workspace type: %s", workspace_type)
        return

    try:
        for module_name in module_names:
            importlib.import_module(module_name)
    except Exception:
        logger.warning(
            "Graphs for workspace '%s' not available",
            workspace_type,
            exc_info=True,
        )
        return

    _LOADED_WORKSPACES.add(workspace_type)
    logger.info(
        "Loaded %d graph modules for workspace type: %s",
        len(module_names),
        workspace_type,
    )


async def execute_feature_graph(
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Execute a feature graph for any workspace type.

    This is the unified entry point for all workspace features.

    Args:
        workspace_type: Workspace type (thesis, sci, proposal, patent, software_copyright)
        feature_id: Feature identifier (e.g., "literature_management", "paper_analysis")
        payload: Feature execution payload (workspace_id, params, etc.)
        user_id: For memory loading (optional)

    Returns:
        Feature execution result dict

    Raises:
        ValueError: If no graph is registered or execution fails
    """
    from src.services.user_memory_service import build_memory_context

    # Load graphs for workspace type
    _ensure_graphs_loaded(workspace_type)

    # Build workspace context
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    discipline = payload.get("workspace_discipline")

    # Load user memory
    memory_text: str | None = None
    if user_id:
        memory_text = await build_memory_context(
            str(user_id),
            workspace_id or None,
            current_context=_derive_feature_memory_context(payload),
        )

    # Build system prompt
    system_prompt = _build_system_prompt(
        workspace_name=workspace_name,
        workspace_type=workspace_type,
        discipline=discipline,
        memory_text=memory_text,
    )

    # Build initial state
    initial_state: dict[str, Any] = {
        "messages": [SystemMessage(content=system_prompt)],
        "workspace_id": workspace_id,
        "workspace_type": workspace_type,
        "discipline": discipline,
        "memory_context": memory_text,
    }

    lookup_key = f"{workspace_type}.{feature_id}"

    if lookup_key not in _FEATURE_GRAPH_REGISTRY:
        raise ValueError(
            f"No LangGraph sub-graph registered for feature '{feature_id}' "
            f"in workspace '{workspace_type}' (available: {list(_FEATURE_GRAPH_REGISTRY.keys())})"
        )

    graph_fn = _FEATURE_GRAPH_REGISTRY[lookup_key]

    try:
        return await graph_fn(initial_state, payload)
    except Exception:
        logger.exception("Feature graph execution failed")
        raise


def _build_system_prompt(
    workspace_name: str,
    workspace_type: str,
    discipline: str | None,
    memory_text: str | None,
) -> str:
    """Build system prompt with memory injection."""
    type_labels = {
        "sci": "学术论文（SCI/EI）",
        "thesis": "学位论文",
        "proposal": "研究计划",
        "software_copyright": "软件著作权申请",
        "patent": "专利申请",
    }
    type_label = type_labels.get(workspace_type, workspace_type)

    parts = [
        f"你是问津 (Wenjin) 的 {type_label} 工作助手。",
        f"当前工作区：{workspace_name}",
        f"工作区类型：{workspace_type.upper()}",
        "",
        "执行规范：",
        "- 输出使用中文，专业术语可保留英文原文",
        "- 保持学术规范，引用、实验结论和事实表述需有据可查",
        "- 优先生成可直接落稿、可直接执行、可直接评审的内容，避免空泛套话",
        "- 结构化输出优先（使用标题、列表、表格）",
        "- 区分已知事实、合理推断和待补充信息；不要把待确认内容写成既定事实",
        "- 如果上下文不足，保守生成并明确标注哪些部分需要用户补充实际数据或进一步核验",
    ]
    if discipline:
        parts.insert(2, f"学科领域：{discipline}")
    if memory_text:
        parts.append(f"\n{memory_text}")
    return "\n".join(parts)


async def execute_thesis_feature_graph(
    feature_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for thesis workspace feature execution."""
    return await execute_feature_graph("thesis", feature_id, payload, user_id=user_id)


def _derive_feature_memory_context(payload: dict[str, Any]) -> str | None:
    """Extract a compact feature context hint to rank memory injection."""
    params = payload.get("params")
    if not isinstance(params, dict):
        return None

    snippets: list[str] = []
    for key in _FEATURE_MEMORY_CONTEXT_KEYS:
        value = params.get(key)
        if isinstance(value, str):
            normalized = " ".join(value.split())
            if normalized:
                snippets.append(normalized)
            continue
        if isinstance(value, list):
            normalized_items = [
                " ".join(str(item).split())
                for item in value
                if str(item).strip()
            ]
            if normalized_items:
                snippets.append("；".join(normalized_items))

    if not snippets:
        return None

    deduped_snippets = list(dict.fromkeys(snippets))
    context = "\n".join(deduped_snippets[:5]).strip()
    if len(context) > 2400:
        return context[:2399].rstrip() + "…"
    return context
