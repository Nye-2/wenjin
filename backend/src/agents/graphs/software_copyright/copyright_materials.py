"""Copyright Materials sub-graph — deterministic materials checklist generation.

Pipeline: extract parameters -> build payload -> sync linked LaTeX output
"""

from __future__ import annotations

from typing import Any

from src.agents.graphs._shared import _normalize_list, _read_payload_params
from src.agents.workspace_lead_agent import register_feature_graph
from src.task.progress import get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    upsert_runtime_block,
)
from src.task.runtime_blocks import (
    emit_bound_runtime as _emit_bound_runtime,
)
from src.workspace_features.latex_sync import sync_software_materials_payload
from src.workspace_features.services.software_copyright_feature_service import (
    _build_required_materials,
    _build_review_checklist,
    build_copyright_materials_payload,
)

__all__ = ["_build_required_materials", "_build_review_checklist", "copyright_materials_graph"]


@register_feature_graph("copyright_materials", workspace_type="software_copyright")
async def copyright_materials_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute copyright materials checklist generation.

    Pipeline: extract params -> build checklist -> build output
    This is a deterministic generation (no LLM needed).
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    workspace_discipline = str(payload.get("workspace_discipline", ""))
    params = _read_payload_params(payload)

    # Step 1: Extract parameters (per handoff document)
    software_name = str(
        params.get("software_name")
        or workspace_name
        or "待确认软件名称"
    ).strip()
    version = str(
        params.get("version")
        or params.get("software_version")
        or "V1.0"
    ).strip()
    applicant_name = str(params.get("applicant_name") or "待确认申请主体").strip()
    completion_date = str(params.get("completion_date") or "待确认开发完成日期").strip()
    highlights = _normalize_list(params.get("highlights"))
    target_platforms = _normalize_list(params.get("target_platforms"))
    source_modules = _normalize_list(params.get("source_modules"))
    runtime = get_runtime_state()

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "materials-profile",
                "kind": "metrics",
                "title": "软件画像",
                "entries": [
                    {"label": "软件名称", "value": software_name},
                    {"label": "版本", "value": version},
                    {"label": "平台", "value": str(len(target_platforms))},
                    {"label": "模块", "value": str(len(source_modules))},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="基础信息已整理",
            description="已整理软件名称、版本和申请主体。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成申请材料清单...",
            current_phase="materials",
            stage_transition=True,
        )

    result = await build_copyright_materials_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_description=workspace_description,
        workspace_discipline=workspace_discipline,
        software_name=software_name,
        version=version,
        applicant_name=applicant_name,
        completion_date=completion_date,
        highlights=highlights,
        target_platforms=target_platforms,
        source_modules=source_modules,
    )
    required_materials = result.get("required_materials", [])
    review_checklist = result.get("review_checklist", [])

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "required-materials",
                "kind": "list",
                "title": "材料清单",
                "items": [
                    {
                        "title": str(item.get("title") or item.get("id") or "材料项"),
                        "description": "、".join(str(field) for field in (item.get("required_fields") or [])[:3]),
                        "meta": str(item.get("status") or ""),
                    }
                    for item in required_materials[:8]
                    if isinstance(item, dict)
                ],
            },
        )
        upsert_runtime_block(
            runtime,
            {
                "id": "review-checklist",
                "kind": "list",
                "title": "核对清单",
                "items": [
                    {"title": str(item), "description": ""}
                    for item in review_checklist[:6]
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="材料清单已生成",
            description=f"已输出 {len(required_materials)} 个材料项和核对清单。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理软著材料产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    sync_result = await sync_software_materials_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        payload=result,
    )
    return {
        **result,
        **sync_result.as_payload(),
    }
