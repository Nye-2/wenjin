"""Paper Analysis sub-graph — LLM-powered structured analysis of academic papers.

Pipeline: parse parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.feature_leader.graph_registry import register_feature_graph
from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.workspace_features.services import build_paper_analysis_payload

logger = logging.getLogger(__name__)


@register_feature_graph("paper_analysis", workspace_type="sci")
async def paper_analysis_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute paper analysis with LLM-enhanced analysis.

    Pipeline:
        1. Parse parameters
        2. Call service layer (build_paper_analysis_payload)
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = _read_payload_params(payload)

    # Extract parameters (per handoff document)
    reference_id = _read_optional_str(params.get("reference_id"))
    paper_title = str(
        params.get("paper_title")
        or params.get("title")
        or payload.get("workspace_name")
        or "未命名论文"
    )
    paper_abstract = _read_optional_str(
        params.get("paper_abstract") or payload.get("workspace_description")
    )
    preferred_model = _read_optional_str(params.get("model_id"))

    # Call service layer
    result = await build_paper_analysis_payload(
        workspace_id=workspace_id,
        reference_id=reference_id,
        paper_title=paper_title,
        paper_abstract=paper_abstract,
        preferred_model=preferred_model,
    )

    # Build structured output
    return {
        "reference_id": result.get("reference_id"),
        "paper_title": result.get("paper_title"),
        "analysis_mode": result.get("analysis_mode", "llm"),
        "sections": result.get("sections", {}),
        "summary": result.get("summary", ""),
        "quality_assessment": result.get("quality_assessment", {}),
        "recommendations": result.get("recommendations", []),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
