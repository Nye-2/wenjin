"""Background Research sub-graph — LLM-powered background research generation.

Pipeline: extract parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_background_research_payload

logger = logging.getLogger(__name__)


@register_feature_graph("background_research", workspace_type="proposal")
async def background_research_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute background research generation with LLM-enhanced analysis.

    Pipeline:
        1. Extract parameters
        2. Call service layer
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    params = _read_payload_params(payload)

    # Step 1: Extract parameters (per handoff document)
    keywords = str(
        params.get("keywords")
        or workspace_name
        or "未指定主题"
    ).strip()
    industry_scope = str(params.get("industry_scope") or "相关领域").strip()
    time_range = str(params.get("time_range") or "近5年").strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    # Step 2: Call service layer
    result = await build_background_research_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        keywords=keywords,
        industry_scope=industry_scope,
        time_range=time_range,
        preferred_model=preferred_model,
    )

    # Step 3: Build structured output
    return {
        "keywords": result.get("keywords", keywords),
        "industry_scope": result.get("industry_scope", industry_scope),
        "time_range": result.get("time_range", time_range),
        "sections": result.get("sections", []),
        "references": result.get("references"),
        "generation_mode": result.get("generation_mode", "llm"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
