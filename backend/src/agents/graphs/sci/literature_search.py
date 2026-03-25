"""Literature Search sub-graph — LLM-powered literature search.

Pipeline: extract parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_literature_search_payload

logger = logging.getLogger(__name__)


@register_feature_graph("literature_search", workspace_type="sci")
async def literature_search_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute literature search with LLM-enhanced synthesis.

    Pipeline:
        1. Extract parameters from payload
        2. Call service layer
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = _read_payload_params(payload)

    # Extract parameters (per handoff document)
    query = str(
        params.get("query")
        or params.get("keywords")
        or payload.get("workspace_description")
        or payload.get("workspace_name")
        or "研究主题"
    )
    discipline = str(
        params.get("discipline")
        or payload.get("workspace_discipline")
        or ""
    )
    preferred_model = _read_optional_str(params.get("model_id"))

    # Call service layer
    result = await build_literature_search_payload(
        workspace_id=workspace_id,
        query=query,
        discipline=discipline or None,
        preferred_model=preferred_model,
    )

    # Build structured output
    return {
        "query": result.get("query", query),
        "discipline": result.get("discipline", discipline),
        "papers": result.get("papers", []),
        "top_hits": result.get("top_hits", []),
        "filters": result.get("filters", {}),
        "summary": result.get("summary", ""),
        "search_strategy": result.get("search_strategy", "llm_synthesis"),
        "generated_at": result.get("generated_at"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
    }
