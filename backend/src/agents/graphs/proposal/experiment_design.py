"""Proposal experiment-design sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_experiment_design_payload


@register_feature_graph("experiment_design", workspace_type="proposal")
async def experiment_design_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate experiment-design output for proposal workspaces."""
    workspace_name = str(payload.get("workspace_name", "")).strip()
    workspace_description = str(payload.get("workspace_description", "")).strip()
    params = _read_payload_params(payload)
    topic = str(params.get("topic") or workspace_name or workspace_description or "研究主题").strip()
    objective = str(params.get("objective") or workspace_description or topic).strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    return await build_experiment_design_payload(
        topic=topic,
        objective=objective,
        preferred_model=preferred_model,
    )
