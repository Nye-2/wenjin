"""SCI Writing sub-graph — LLM-powered academic section writing.

Pipeline: parse parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_int,
    _read_payload_params,
    _read_optional_str,
)
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_sci_writing_payload

logger = logging.getLogger(__name__)

# Section type to display name mapping
SCI_SECTION_MAP = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related_work": "Related Work",
    "methodology": "Methodology",
    "experiments": "Experiments",
    "results": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}

DEFAULT_SECTION = "introduction"
DEFAULT_TARGET_WORDS = 800
DEFAULT_OUTPUT_LANGUAGE = "en"


@register_feature_graph("writing", workspace_type="sci")
async def writing_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute SCI paper writing with LLM-enhanced generation.

    Pipeline:
        1. Parse parameters and extract context
        2. Call service layer
        3. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = _read_payload_params(payload)

    # Extract parameters (per handoff document)
    paper_title = str(
        params.get("paper_title")
        or params.get("title")
        or workspace_name
        or "未命名论文"
    )
    section_type = str(
        params.get("section_type")
        or params.get("section")
        or DEFAULT_SECTION
    ).lower()

    # Validate section type
    if section_type not in SCI_SECTION_MAP:
        section_type = DEFAULT_SECTION

    target_words = _read_optional_int(params.get("target_words")) or DEFAULT_TARGET_WORDS
    context_artifact_ids = _normalize_list(params.get("context_artifact_ids"))
    preferred_model = _read_optional_str(params.get("model_id"))

    # Call service layer
    result = await build_sci_writing_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        paper_title=paper_title,
        section_type=section_type,
        target_words=target_words,
        context_artifact_ids=context_artifact_ids,
        preferred_model=preferred_model,
    )

    # Build output
    section_title = str(
        result.get("section_title")
        or SCI_SECTION_MAP.get(section_type, section_type.title())
    )

    return {
        "section_type": section_type,
        "section_title": section_title,
        "content": result.get("content", ""),
        "outline": result.get("outline", []),
        "references": result.get("references", []),
        "word_count": result.get("word_count", 0),
        "writing_mode": result.get("writing_mode", "llm"),
        "output_language": result.get("output_language", DEFAULT_OUTPUT_LANGUAGE),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
    }
