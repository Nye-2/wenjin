"""WorkspaceLeadAgent -- Unified LangGraph orchestrator for all workspace types.

This module replaces thesis_lead_agent.py as the central registry and executor
for LangGraph sub-graphs across all workspace types (thesis, sci, proposal,
patent, software_copyright).

Key features:
- Lazy loading of graph modules per workspace type
- Composite registry key: {workspace_type}.{feature_id}
- Backward compatibility with thesis_lead_agent.py imports
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)

# Feature graph registry: composite_key -> async callable(initial_state, payload) -> result
# Key format: "{workspace_type}.{feature_id}" or "{feature_id}" (backward compat)
_FEATURE_GRAPH_REGISTRY: dict[str, Callable] = {}
_LOADED_WORKSPACES: set[str] = set()


def register_feature_graph(feature_id: str, workspace_type: str | None = None):
    """Decorator to register a feature graph function.

    Args:
        feature_id: Unique identifier for the feature (e.g., "literature_search")
        workspace_type: Workspace type for multi-workspace support (e.g., "sci", "patent")
                         If None, assumes backward compatibility with thesis graphs.

    Returns:
        Decorator function that registers the graph and returns it unchanged.
    """
    def decorator(fn: Callable) -> Callable:
        # Build composite key
        if workspace_type:
            key = f"{workspace_type}.{feature_id}"
        else:
            # Backward compat: use feature_id only for thesis
            key = feature_id

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

    _LOADED_WORKSPACES.add(workspace_type)

    workspace_modules = {
        "thesis": "src.agents.graphs.thesis",
        "sci": "src.agents.graphs.sci",
        "proposal": "src.agents.graphs.proposal",
        "patent": "src.agents.graphs.patent",
        "software_copyright": "src.agents.graphs.software_copyright",
    }

    module_name = workspace_modules.get(workspace_type)
    if not module_name:
        logger.warning("Unknown workspace type: %s", workspace_type)
        return

    try:
        importlib.import_module(module_name)
        logger.info("Loaded graphs for workspace type: %s", workspace_type)
    except ImportError:
        logger.warning(
            "Graphs for workspace '%s' not available",
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
        skill_user_id: skill_user_id from payload or created_by
        created_by: Optional creator fallback

        handler_key: Optional handler key for metadata

    Returns:
        Feature execution result dict

    Raises:
        ValueError: If no graph is registered or execution fails
    """
    from src.agents.middleware.memory import (
        format_knowledge_for_prompt,
        load_user_memory,
    )
    from src.services.knowledge_service import KnowledgeService
    from src.database import get_db_session

    # Load graphs for workspace type
    _ensure_graphs_loaded(workspace_type)

    # Build workspace context
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    discipline = payload.get("workspace_discipline")

    workspace_type_from_payload = workspace_type

    # Load user memory
    memory_items: list[dict] = []
    if user_id:
        memory_items = await load_user_memory(user_id, workspace_id)
    memory_text = format_knowledge_for_prompt(memory_items) if memory_items else None

    # Build system prompt
    system_prompt = _build_system_prompt(
        workspace_name=workspace_name,
        workspace_type=workspace_type_from_payload,
        discipline=discipline,
        memory_text=memory_text,
    )
    # Build initial state
    initial_state: dict[str, Any] = {
        "messages": [SystemMessage(content=system_prompt)],
        "workspace_id": workspace_id,
        "workspace_type": workspace_type_from_payload,
        "discipline": discipline,
        "knowledge_context": memory_text,
    }
    # Lookup graph: workspace_type.feature_id first, then feature_id (backward compat)
    lookup_key = f"{workspace_type_from_payload}.{feature_id}"
    if lookup_key not in _FEATURE_GRAPH_REGISTRY:
        lookup_key = feature_id

    if lookup_key not in _FEATURE_GRAPH_REGISTRY:
        raise ValueError(
            f"No LangGraph sub-graph registered for feature '{feature_id}' "
            f"in workspace '{workspace_type_from_payload}' (available: {list(_FEATURE_GRAPH_REGISTRY.keys())})"
        )
    graph_fn = _FEATURE_GRAPH_REGISTRY[lookup_key]
    return await graph_fn(initial_state, payload)


    raise
    except Exception as exc:
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


async def _build_memory_context(
    user_id: str | None,
    workspace_id: str | None,
) -> str | None:
    """Build memory context for LLM prompts (placeholder)."""
    if not user_id:
        return None
    from src.services.knowledge_service import KnowledgeService
    from src.database import get_db_session
    try:
        async with get_db_session() as db:
            service = KnowledgeService(db)
            knowledge_items = await service.list_knowledge(user_id=user_id)
            # Filter by workspace context
            if workspace_id:
                knowledge_items = [
                k for k in knowledge_items
                if str(k.get("workspace_id") or workspace_id == "all"
                or k.get("workspace_id") is None
            ]
        if not knowledge_items:
            return None
        # Format for prompt
        return format_knowledge_for_prompt(knowledge_items)
    except Exception:
        logger.warning("Failed to load memory context", exc_info=True)
        return None
