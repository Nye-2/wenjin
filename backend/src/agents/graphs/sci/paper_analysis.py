"""Paper Analysis sub-graph — LLM-powered structured analysis of academic papers.

Pipeline: parse parameters -> load paper data -> parallel LLM analysis -> quality assessment -> synthesis and recommendations

"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph
from src.agents.graphs._shared import (
    detect_generation_mode,
    parse_json_response,
)

from src.workspace_features.services import build_paper_analysis_payload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section prompts for parallel LLM analysis
# ---------------------------------------------------------------------------
SECTION_PROMPTS = {
    "methodology": """Analyze the research methodology of the paper. Return JSON.

Paper: {paper_info}

Focus on: research design, data sources, analysis methods, and validity threats.

Return: {{"title": "Methodology", "content": "Description", "key_points": ["point1", "point2"]}}""",

    "experiments": """Analyze the experimental design of the paper. Return JSON.

Paper: {paper_info}

Focus on: experimental setup, baselines, metrics, and reproducibility.
Return: {{"title": "Experiments", "content": "Description", "key_points": ["point1", "point2"]}}""",

    "conclusions": """Analyze the key findings and conclusions of this paper. Return JSON.

Paper: {paper_info}

Focus on: main results, contributions, limitations, and future work.
Return: {{"title": "Conclusions", "content": "Description", "key_points": ["point1", "point2"]}}""",

    "innovations": """Analyze the innovations and contributions of this paper. Return JSON.

Paper: {paper_info}

Focus on: novel methods, theoretical contributions, practical applications, and limitations.
Return: {{"title": "Innovations", "content": "Description", "key_points": ["point1", "point2"]}}""",
}


def _read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


}


@register_feature_graph("paper_analysis")
async def paper_analysis_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute paper analysis with LLM-enhanced analysis.

    Pipeline:
        1. Parse parameters
        2. Call service layer (build_paper_analysis_payload)
        3. Determine generation mode from service response
        4. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    params = payload.get("params", {})
    paper_id = _read_optional_str(params.get("paper_id"))
    paper_title = str(
        params.get("paper_title")
        or params.get("title")
        or payload.get("workspace_name")
        or "未命名论文"
    )
    paper_abstract = _read_optional_str(params.get("paper_abstract") or payload.get("workspace_description"))
    preferred_model = _read_optional_str(params.get("model_id"))
    memory_context = initial_state.get("knowledge_context")

    # Call service layer - handles LLM + fallback internally
    result = await build_paper_analysis_payload(
        workspace_id=workspace_id,
        paper_id=paper_id,
        paper_title=paper_title,
        paper_abstract=paper_abstract,
        preferred_model=preferred_model,
    )
    # Determine generation mode from service response
    generation_mode = str(result.get("analysis_mode") or "template_fallback")
    # Build structured output (matching thesis graph patterns)
    return {
        "paper_id": result.get("paper_id"),
        "paper_title": result.get("paper_title"),
        "analysis_mode": generation_mode,
        "sections": result.get("sections", {}),
        "summary": result.get("summary", ""),
        "quality_assessment": result.get("quality_assessment", {}),
        "recommendations": result.get("recommendations", []),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at", datetime.now(tz=timezone.utc).isoformat()),
    }
