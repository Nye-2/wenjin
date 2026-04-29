"""SCI peer-review sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.feature_leader.graph_registry import register_feature_graph
from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.workspace_features.services import build_peer_review_payload


@register_feature_graph("peer_review", workspace_type="sci")
async def peer_review_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate a peer-review style assessment."""
    params = _read_payload_params(payload)
    paper_title = str(
        params.get("paper_title")
        or payload.get("workspace_name")
        or "Untitled Paper"
    ).strip()
    manuscript_excerpt = str(params.get("manuscript_excerpt") or "").strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    return await build_peer_review_payload(
        paper_title=paper_title,
        manuscript_excerpt=manuscript_excerpt,
        preferred_model=preferred_model,
    )
