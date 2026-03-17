"""Patent Outline sub-graph — LLM-powered patent specification generation.

Pipeline: extract parameters -> call service layer -> parallel LLM generation -> claims drafting -> evidence checklist

Falls back to template mode if LLM unavailable.
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

logger = logging.getLogger(__name__)


@register_feature_graph("patent_outline")
async def patent_outline_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute patent outline with LLM-enhanced generation.

    Pipeline:
        1. Extract parameters from context
        2. Call service layer for section and claims generation
        3. Determine generation mode from service response
        4. Build structured output

    Falls back to template mode if LLM unavailable.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = payload.get("params", {})
    memory_context = initial_state.get("knowledge_context")

    # Step 1: Parameter extraction
    innovation_description = str(
        params.get("innovation_description")
        or workspace_description
        or workspace_name
        or "创新技术"
    )
    technical_field = str(params.get("technical_field", ""))
    application_scenario = str(params.get("application_scenario", ""))
    implementation_method = str(params.get("implementation_method", ""))
    preferred_model = _read_optional_str(params.get("model_id"))
    normalized_innovation = _normalize_text(innovation_description)
    normalized_field = _normalize_text(technical_field)
    normalized_scenario = _normalize_text(application_scenario)
    normalized_implementation = _normalize_text(implementation_method)
    }
    memory_text = f"\n用户记忆上下文: {memory_context}" if memory_context else ""

    # Step 2: Call service layer
    from src.workspace_features.services.patent_feature_service import build_patent_outline_payload
        result = await build_patent_outline_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        innovation_description=normalized_innovation,
        technical_field=normalized_field,
        application_scenario=normalized_scenario,
        implementation_method=normalized_implementation,
        preferred_model=preferred_model,
    )
    # Step 3: Determine generation mode from service response
    generation_mode = str(result.get("generation_mode") or "template_fallback")
    sections = result.get("sections", [])
    claims_draft = result.get("claims_draft", {})
    evidence_points = result.get("evidence_points_needed", [])
    model_id = result.get("model_id")
    generation_error = result.get("generation_error")
    generated_at = result.get("generated_at")

    }
    else:
        # Template fallback
        generation_mode = "template_fallback"
        sections = []
        claims_draft = {}
        evidence_points = []
        model_id = None
        generation_error = None
        generated_at = datetime.now(tz=timezone.utc).isoformat()
    }
    return {
        "innovation_description": normalized_innovation,
        "technical_field": normalized_field,
        "sections": sections,
        "claims_draft": claims_draft,
        "evidence_points_needed": evidence_points,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "generated_at": generated_at,
    }
