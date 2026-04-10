"""Proposal Outline sub-graph — LLM-powered proposal outline generation.

Pipeline: extract parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import (
    _read_optional_int,
    _read_optional_str,
    _read_payload_params,
)
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.latex_sync import sync_proposal_outline_payload
from src.workspace_features.services import build_proposal_outline_payload

logger = logging.getLogger(__name__)


@register_feature_graph("proposal_outline", workspace_type="proposal")
async def proposal_outline_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute proposal outline generation with LLM-enhanced analysis.

    Pipeline:
        1. Extract parameters
        2. Call service layer
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    params = _read_payload_params(payload)

    # Step 1: Extract parameters (per handoff document)
    topic = str(
        params.get("topic")
        or workspace_name
        or "未命名项目"
    ).strip()
    proposal_type = str(params.get("proposal_type", "other"))
    period_months = _read_optional_int(params.get("period_months"))
    preferred_model = _read_optional_str(params.get("model_id"))

    # Step 2: Call service layer
    result = await build_proposal_outline_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        topic=topic,
        proposal_type=proposal_type,
        period_months=period_months,
        preferred_model=preferred_model,
    )
    sync_result = await sync_proposal_outline_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        payload=result,
    )

    # Step 3: Build structured output
    return {
        "topic": result.get("topic", topic),
        "proposal_type": result.get("proposal_type", proposal_type),
        "proposal_type_label": result.get("proposal_type_label", "科研项目"),
        "period_months": result.get("period_months", 24),
        "sections": result.get("sections", []),
        "milestones": result.get("milestones", []),
        "risks": result.get("risks", []),
        "generation_mode": result.get("generation_mode", "llm"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
        **sync_result.as_payload(),
    }
