"""ThesisLeadAgent -- LangGraph-based orchestrator for THESIS workspace features."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)

# Feature IDs that this agent can route to
THESIS_FEATURE_IDS = (
    "deep_research",
    "literature_management",
    "opening_research",
    "thesis_writing",
    "figure_generation",
    "compile_export",
)


def _build_system_prompt(
    workspace_name: str,
    discipline: str | None,
    memory_text: str | None,
) -> str:
    """Build system prompt with memory injection."""
    parts = [
        "你是 AcademiaGPT THESIS 工作区的学术助手。",
        f"当前工作区：{workspace_name}",
    ]
    if discipline:
        parts.append(f"学科领域：{discipline}")
    if memory_text:
        parts.append(f"\n{memory_text}")
    return "\n".join(parts)


async def execute_thesis_feature_graph(
    feature_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Entry point: route a thesis feature to its LangGraph sub-graph.

    Args:
        feature_id: One of THESIS_FEATURE_IDS
        payload: Feature execution payload (workspace_id, params, etc.)
        user_id: For memory loading

    Returns:
        Feature execution result dict
    """
    from src.agents.middleware.memory import (
        format_knowledge_for_prompt,
        load_user_memory,
    )

    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    discipline = payload.get("workspace_discipline")

    # Load user memory
    memory_items: list[dict] = []
    if user_id:
        memory_items = await load_user_memory(user_id, workspace_id)
    memory_text = format_knowledge_for_prompt(memory_items) if memory_items else None

    # Build initial state
    system_prompt = _build_system_prompt(workspace_name, discipline, memory_text)

    initial_state: dict[str, Any] = {
        "messages": [SystemMessage(content=system_prompt)],
        "workspace_id": workspace_id,
        "workspace_type": "thesis",
        "discipline": discipline,
        "knowledge_context": memory_text,
    }

    # Route to feature-specific graph
    graph_fn = _FEATURE_GRAPH_REGISTRY.get(feature_id)
    if graph_fn is None:
        raise ValueError(f"No LangGraph sub-graph registered for feature: {feature_id}")

    return await graph_fn(initial_state, payload)


# Registry: feature_id -> async callable(initial_state, payload) -> result
_FEATURE_GRAPH_REGISTRY: dict[str, Any] = {}


def register_feature_graph(feature_id: str):
    """Decorator to register a feature graph function."""
    def decorator(fn):
        _FEATURE_GRAPH_REGISTRY[feature_id] = fn
        return fn
    return decorator
