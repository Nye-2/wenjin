"""SCI journal-recommendation sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.graphs._shared import _read_optional_str, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_journal_recommend_payload


@register_feature_graph("journal_recommend", workspace_type="sci")
async def journal_recommend_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Recommend journals for the current SCI manuscript."""
    params = _read_payload_params(payload)
    paper_title = str(
        params.get("paper_title")
        or payload.get("workspace_name")
        or "Untitled Paper"
    ).strip()
    abstract = str(
        params.get("abstract")
        or payload.get("workspace_description")
        or ""
    ).strip()
    discipline = str(
        params.get("discipline")
        or payload.get("workspace_discipline")
        or ""
    ).strip()
    preferred_model = _read_optional_str(params.get("model_id"))

    return await build_journal_recommend_payload(
        paper_title=paper_title,
        abstract=abstract,
        discipline=discipline or None,
        preferred_model=preferred_model,
    )
