"""Prior Art Search sub-graph — LLM-powered patent prior art analysis.

Pipeline: extract parameters -> call service layer -> build output.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.feature_leader.graph_registry import register_feature_graph
from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_str,
    _read_payload_params,
)
from src.workspace_features.services import build_prior_art_search_payload

logger = logging.getLogger(__name__)


@register_feature_graph("prior_art_search", workspace_type="patent")
async def prior_art_search_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute prior art search with LLM-enhanced analysis.

    Pipeline:
        1. Extract parameters
        2. Call service layer for analysis
        3. Build structured output

    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = _read_payload_params(payload)

    # Step 1: Parameter extraction (per handoff document)
    keywords = _normalize_list(params.get("keywords"), max_items=5)
    ipc_codes = _normalize_list(params.get("ipc_codes"), max_items=5)
    time_range = str(params.get("time_range") or "近5年").strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    # Step 2: Call service layer
    result = await build_prior_art_search_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        keywords=keywords,
        ipc_codes=ipc_codes,
        time_range=time_range,
        preferred_model=preferred_model,
    )

    # Step 3: Build structured output
    return {
        "keywords": result.get("keywords", keywords),
        "ipc_codes": result.get("ipc_codes", ipc_codes),
        "time_range": result.get("time_range", time_range),
        "search_scope": result.get("search_scope", {}),
        "comparison_table": result.get("comparison_table", []),
        "novelty_risks": result.get("novelty_risks", []),
        "avoidance_suggestions": result.get("avoidance_suggestions", []),
        "next_steps": result.get("next_steps", []),
        "generation_mode": result.get("generation_mode", "llm"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
