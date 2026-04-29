"""SCI framework-outline sub-graph."""

from __future__ import annotations

from typing import Any

from src.agents.feature_leader.graph_registry import register_feature_graph
from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_str,
    _read_payload_params,
)
from src.workspace_features.latex_sync import sync_sci_framework_outline_payload
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

    result = await build_framework_outline_payload(
        workspace_id=workspace_id,
        paper_title=paper_title,
        topic=topic,
        context_artifact_ids=context_artifact_ids,
        preferred_model=preferred_model,
    )
    sync_result = await sync_sci_framework_outline_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        payload=result,
    )
    return {
        "schema_version": result.get("schema_version", "v1"),
        "document_type": result.get("document_type", "framework_outline"),
        "output_language": result.get("output_language", "en"),
        "paper_title": result.get("paper_title", paper_title),
        "topic": result.get("topic", topic),
        "abstract": result.get("abstract", ""),
        "keywords": result.get("keywords", []),
        "sections": result.get("sections", []),
        "contributions": result.get("contributions", []),
        "context_artifact_ids": result.get("context_artifact_ids", context_artifact_ids),
        "context_artifacts_count": result.get("context_artifacts_count", len(context_artifact_ids)),
        "generated_at": result.get("generated_at"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generation_mode": result.get("generation_mode", "template"),
        **sync_result.as_payload(),
    }
