"""Patent Outline sub-graph — LLM-powered patent specification generation.

Pipeline: extract parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import _normalize_text, _read_optional_str
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_patent_outline_payload

logger = logging.getLogger(__name__)


@register_feature_graph("patent_outline", workspace_type="patent")
async def patent_outline_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute patent outline with LLM-enhanced generation.

    Pipeline:
        1. Extract parameters from context
        2. Call service layer for section and claims generation
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = payload.get("params", {})

    # Step 1: Parameter extraction (per handoff document)
    innovation_description = _normalize_text(
        params.get("innovation_description"),
        fallback=workspace_description or workspace_name or "创新技术",
    )
    technical_field = _normalize_text(params.get("technical_field"), fallback="")
    application_scenario = _normalize_text(params.get("application_scenario"), fallback="")
    implementation_method = _normalize_text(params.get("implementation_method"), fallback="")
    preferred_model = _read_optional_str(params.get("model_id"))

    # Step 2: Call service layer
    result = await build_patent_outline_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        innovation_description=innovation_description,
        technical_field=technical_field,
        application_scenario=application_scenario,
        implementation_method=implementation_method,
        preferred_model=preferred_model,
    )

    # Step 3: Build structured output
    return {
        "innovation_description": result.get("innovation_description", innovation_description),
        "technical_field": result.get("technical_field", technical_field),
        "sections": result.get("sections", []),
        "claims_draft": result.get("claims_draft", {}),
        "evidence_points_needed": result.get("evidence_points_needed", []),
        "generation_mode": result.get("generation_mode", "template_fallback"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
