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
    workspace_id = str(payload.get("workspace_id", "")).strip()
    workspace_name = str(payload.get("workspace_name", "")).strip()
    workspace_description = str(payload.get("workspace_description", "")).strip()
    params = _read_payload_params(payload)
    topic = str(params.get("topic") or workspace_name or workspace_description or "研究主题").strip()
    objective = str(params.get("objective") or workspace_description or topic).strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    result = await build_experiment_design_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        topic=topic,
        objective=objective,
        preferred_model=preferred_model,
    )
    return {
        "topic": result.get("topic", topic),
        "objective": result.get("objective", objective),
        "hypotheses": result.get("hypotheses", []),
        "variables": result.get("variables", []),
        "procedure": result.get("procedure", []),
        "evaluation": result.get("evaluation", []),
        "risks": result.get("risks", []),
        "latex_project_id": result.get("latex_project_id"),
        "main_file": result.get("main_file"),
        "section_file": result.get("section_file"),
        "section_map": result.get("section_map", {}),
        "sync_conflicts": result.get("sync_conflicts", []),
        "generation_mode": result.get("generation_mode", "llm"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
