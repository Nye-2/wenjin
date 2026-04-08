"""Technical Description sub-graph — LLM-powered software copyright technical description document generation.

Pipeline: extract parameters -> call service layer -> build output
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import (
    _normalize_list,
    _read_optional_str,
    _read_payload_params,
)
from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_technical_description_payload

logger = logging.getLogger(__name__)

COPYRIGHT_OUTPUT_LANGUAGE = "zh"


@register_feature_graph("technical_description", workspace_type="software_copyright")
async def technical_description_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute technical description generation with LLM-enhanced analysis.

    Pipeline:
        1. Extract parameters
        2. Load existing copyright_materials for defaults
        3. Call service layer
        4. Build structured output
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = _read_payload_params(payload)

    # Step 1: Extract parameters (per handoff document)
    software_name = str(
        params.get("software_name")
        or workspace_name
        or "待确认软件"
    ).strip()
    version = str(
        params.get("version")
        or params.get("software_version")
        or "V1.0"
    ).strip()
    core_modules = _normalize_list(params.get("core_modules"))
    deployment_architecture = str(params.get("deployment_architecture") or "B/S架构").strip()
    database_middleware = _normalize_list(params.get("database_middleware"))
    interface_protocols = _normalize_list(params.get("interface_protocols"))
    highlights = _normalize_list(params.get("highlights"))
    preferred_model = _read_optional_str(params.get("model_id"))

    # Step 2: Call service layer
    # Service layer also handles loading existing copyright_materials for defaults
    result = await build_technical_description_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        software_name=software_name,
        version=version,
        core_modules=core_modules,
        deployment_architecture=deployment_architecture,
        database_middleware=database_middleware,
        interface_protocols=interface_protocols,
        highlights=highlights,
        preferred_model=preferred_model,
    )

    # Step 3: Build structured output
    return {
        "software_profile": result.get("software_profile", {}),
        "sections": result.get("sections", {}),
        "latex_project_id": result.get("latex_project_id"),
        "main_file": result.get("main_file"),
        "section_map": result.get("section_map", {}),
        "sync_conflicts": result.get("sync_conflicts", []),
        "generation_mode": result.get("generation_mode", "llm"),
        "model_id": result.get("model_id"),
        "generation_error": result.get("generation_error"),
        "generated_at": result.get("generated_at"),
        "upgrade": result.get("upgrade", {
            "auto_upgrade": False,
            "can_regenerate_with_llm": False,
            "last_error": result.get("generation_error"),
        }),
    }
