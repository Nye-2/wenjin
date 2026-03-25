"""WorkspaceLeadAgent -- Unified LangGraph orchestrator for all workspace types.

This module replaces thesis_lead_agent.py as the central registry and executor
for LangGraph sub-graphs across all workspace types (thesis, sci, proposal,
patent, software_copyright).

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

logger = logging.getLogger(__name__)

__all__ = [
    "THESIS_FEATURE_IDS",
    "execute_feature_graph",
    "execute_thesis_feature_graph",
    "register_feature_graph",
]

THESIS_FEATURE_IDS = (
    "deep_research",
    "literature_management",
    "opening_research",
    "thesis_writing",
    "figure_generation",
    "compile_export",
)

# Type alias for feature graph functions
FeatureGraphFn = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]

# Feature graph registry: composite_key -> async callable(initial_state, payload) -> result
# Key format: "{workspace_type}.{feature_id}" (e.g., "thesis.literature_management")
_FEATURE_GRAPH_REGISTRY: dict[str, FeatureGraphFn] = {}
_LOADED_WORKSPACES: set[str] = set()
_WORKSPACE_GRAPH_MODULES: dict[str, tuple[str, ...]] = {
    "thesis": (
        "src.agents.graphs.thesis.deep_research",
        "src.agents.graphs.thesis.literature_management",
        "src.agents.graphs.thesis.opening_research",
        "src.agents.graphs.thesis.thesis_writing",
        "src.agents.graphs.thesis.figure_generation",
        "src.agents.graphs.thesis.compile_export",
    ),
    "sci": (
        "src.agents.graphs.sci.literature_search",
        "src.agents.graphs.sci.paper_analysis",
        "src.agents.graphs.sci.writing",
        "src.agents.graphs.sci.literature_review",
        "src.agents.graphs.sci.framework_outline",
        "src.agents.graphs.sci.peer_review",
        "src.agents.graphs.sci.journal_recommend",
    ),
    "proposal": (
        "src.agents.graphs.proposal.proposal_outline",
        "src.agents.graphs.proposal.background_research",
        "src.agents.graphs.proposal.experiment_design",
    ),
    "patent": (
        "src.agents.graphs.patent.patent_outline",
        "src.agents.graphs.patent.prior_art_search",
    ),
    "software_copyright": (
        "src.agents.graphs.software_copyright.copyright_materials",
        "src.agents.graphs.software_copyright.technical_description",
    ),
}


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


def _ensure_graphs_loaded(workspace_type: str) -> None:
    """Lazy-load graph modules for a specific workspace type.

    Each workspace type's graphs are loaded independently, preventing
    errors in one workspace from affecting others.

    Args:
        workspace_type: Workspace type (thesis, sci, proposal, patent, software_copyright)
    """
    if workspace_type in _LOADED_WORKSPACES:
        return

    module_names = _WORKSPACE_GRAPH_MODULES.get(workspace_type)
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
    from src.services.user_memory_service import (
        format_knowledge_for_prompt,
        load_user_memory,
    )

    # Load graphs for workspace type
    _ensure_graphs_loaded(workspace_type)

    # Build workspace context
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    discipline = payload.get("workspace_discipline")

    # Load user memory
    memory_items: list[dict] = []
    if user_id:
        memory_items = await load_user_memory(user_id, workspace_id)
    memory_text = format_knowledge_for_prompt(memory_items) if memory_items else None

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
    parts = [
        f"你是 AcademiaGPT {workspace_type.upper()} 工作区的智能助手。",
        f"当前工作区：{workspace_name}",
    ]
    if discipline:
        parts.append(f"学科领域： {discipline}")
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
