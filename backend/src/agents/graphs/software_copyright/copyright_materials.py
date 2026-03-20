"""Copyright Materials sub-graph — Deterministic software copyright application materials checklist generation.

Pipeline: extract parameters -> build checklist -> build output

Note: This feature has NO independent service function - business logic is directly in handler.
See handoff document for details.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graphs._shared import _normalize_list, _utc_now_iso
from src.agents.workspace_lead_agent import register_feature_graph
from src.task.progress import emit_runtime_update, get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    runtime_progress_for_phase,
    upsert_runtime_block,
)

logger = logging.getLogger(__name__)

COPYRIGHT_OUTPUT_LANGUAGE = "zh"


async def _emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    runtime = get_runtime_state()
    if runtime is None:
        return
    await emit_runtime_update(
        progress_value=max(runtime_progress_for_phase(runtime), 5),
        message=message,
        current_phase=current_phase,
        runtime=runtime,
        stage_transition=stage_transition,
    )


def _build_required_materials(
    *,
    software_name: str,
    version: str,
    applicant_name: str,
    completion_date: str,
    highlights: list[str],
    target_platforms: list[str],
    source_modules: list[str],
) -> list[dict[str, Any]]:
    """Build a deterministic materials checklist artifact."""
    return [
        {
            "id": "application_form",
            "title": "软件著作权登记申请表",
            "status": "pending",
            "required_fields": [
                f"软件全称：{software_name}",
                f"版本号：{version}",
                f"申请人：{applicant_name}",
                f"开发完成日期：{completion_date}",
            ],
            "tips": [
                "名称需要与产品、原型图、说明文档保持一致。",
                "版本号建议采用 V1.0 / V1.0.0 这格式。",
            ],
        },
        {
            "id": "source_code_excerpt",
            "title": "源程序连续页",
            "status": "pending",
            "required_fields": [
                "准备前后各连续 30 页代码样本",
                "页眉标注软件名称、版本和页码",
                "每页不少于 50 行，核心逻辑优先",
            ],
            "suggested_modules": source_modules or [
                "启动入口与配置加载",
                "核心业务流程",
                "权限与数据持久化",
            ],
        },
        {
            "id": "manual_excerpt",
            "title": "软件说明书/操作手册",
            "status": "pending",
            "required_fields": [
                "包含软件简介、运行环境、主要功能、操作流程、界面截图",
                "截图需要覆盖核心页面与关键流程",
                "说明书名称应与软件全称一致",
            ],
            "recommended_sections": [
                "软件概述",
                "运行环境",
                "功能模块说明",
                "操作步骤",
                "部署与维护",
            ],
        },
        {
            "id": "identity_support",
            "title": "主体与权属证明材料",
            "status": "pending",
            "required_fields": [
                "申请人身份证明/营业执照",
                "委托代理材料（如有）",
                "合作开发协议/权属说明（如有多人或单位参与）",
            ],
            "notes": [
                "如果存在委托开发或合作开发，必须补齐权属归属说明",
                "公司申请时需统一盖章信息与申请表主体名称一致",
            ],
        },
        {
            "id": "feature_summary",
            "title": "软件功能亮点归纳",
            "status": "draft",
            "required_fields": highlights or [
                "核心业务流程",
                "权限与数据管理",
                "结果导出与报表",
            ],
            "platforms": target_platforms or ["Web", "Desktop", "Server"],
        },
    ]


def _build_review_checklist() -> list[str]:
    """Build review checklist for completeness verification."""
    return [
        "软件名称、版本号、申请人保持一致。",
        "截图、说明书标题与软件名称一致",
        "申请表和源代码中的信息必须完全填写",
        "软件功能亮点应具有原创性,不能使用空泛的功能描述",
    ]


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
    params = payload.get("params", {})

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

    # Step 2: Build materials checklist
    required_materials = _build_required_materials(
        software_name=software_name,
        version=version,
        applicant_name=applicant_name,
        completion_date=completion_date,
        highlights=highlights,
        target_platforms=target_platforms,
        source_modules=source_modules,
    )

    # Step 3: Build review checklist
    review_checklist = _build_review_checklist()

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

    # Step 4: Build output
    return {
        "schema_version": "v1",
        "output_language": COPYRIGHT_OUTPUT_LANGUAGE,
        "document_type": "copyright_materials",
        "workspace": {
            "id": workspace_id,
            "name": workspace_name,
            "type": "software_copyright",
            "discipline": workspace_discipline,
        },
        "software_profile": {
            "software_name": software_name,
            "version": version,
            "applicant_name": applicant_name,
            "completion_date": completion_date,
            "description": workspace_description,
            "highlights": highlights,
            "target_platforms": target_platforms,
            "source_modules": source_modules,
        },
        "required_materials": required_materials,
        "review_checklist": review_checklist,
        "next_actions": [
            "补齐基础信息后，先整理说明书目录与截图清单",
            "从核心模块中截取连续代码页，优先选择最能体现原创性的部分",
            "完成初稿后进行一次格式核对，再准备提交材料",
        ],
        "generated_at": _utc_now_iso(),
    }
