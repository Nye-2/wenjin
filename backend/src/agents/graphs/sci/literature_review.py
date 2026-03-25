"""SCI literature-review sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_str,
    _read_payload_params,
)
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_sci_literature_review_payload


@register_feature_graph("literature_review", workspace_type="sci")
async def literature_review_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate a structured literature review for SCI workspaces."""
    workspace_id = str(payload.get("workspace_id", ""))
    params = _read_payload_params(payload)
    topic = str(
        params.get("topic")
        or payload.get("workspace_description")
        or payload.get("workspace_name")
        or "研究主题"
    ).strip()
    discipline = str(
        params.get("discipline")
        or payload.get("workspace_discipline")
        or ""
    ).strip()
    context_artifact_ids = _normalize_list(params.get("context_artifact_ids"))
    preferred_model = _read_optional_str(params.get("model_id"))

    return await build_sci_literature_review_payload(
        workspace_id=workspace_id,
        topic=topic,
        discipline=discipline or None,
        context_artifact_ids=context_artifact_ids,
        preferred_model=preferred_model,
    )
