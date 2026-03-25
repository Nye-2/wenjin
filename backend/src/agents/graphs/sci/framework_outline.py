"""SCI framework-outline sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_str,
    _read_payload_params,
)
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_framework_outline_payload


@register_feature_graph("framework_outline", workspace_type="sci")
async def framework_outline_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate abstract and outline for SCI workspaces."""
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", "")).strip()
    workspace_description = str(payload.get("workspace_description", "")).strip()
    params = _read_payload_params(payload)
    paper_title = str(params.get("paper_title") or workspace_name or "Untitled Paper").strip()
    topic = str(params.get("topic") or workspace_description or paper_title).strip()
    context_artifact_ids = _normalize_list(params.get("context_artifact_ids"))
    preferred_model = _read_optional_str(params.get("model_id"))

    return await build_framework_outline_payload(
        workspace_id=workspace_id,
        paper_title=paper_title,
        topic=topic,
        context_artifact_ids=context_artifact_ids,
        preferred_model=preferred_model,
    )
