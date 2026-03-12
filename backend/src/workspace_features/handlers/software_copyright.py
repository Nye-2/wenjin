"""Concrete handlers for software copyright workspace features."""

from typing import Any

from src.artifacts import ArtifactType
from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.runtime import (
    WorkspaceFeatureExecutionContext,
    register_feature_handler,
)


def _normalize_list(value: Any) -> list[str]:
    """Normalize params values into a non-empty string list."""
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


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
                "版本号建议采用 V1.0 / V1.0.0 这类明确格式。",
            ],
        },
        {
            "id": "source_code_excerpt",
            "title": "源程序连续页",
            "status": "pending",
            "required_fields": [
                "准备前后各连续 30 页代码样本。",
                "页眉标注软件名称、版本和页码。",
                "每页不少于 50 行，核心逻辑优先。",
            ],
            "suggested_modules": source_modules or [
                "启动入口与配置加载",
                "核心业务流程",
                "权限与数据持久化",
            ],
        },
        {
            "id": "manual_excerpt",
            "title": "软件说明书 / 操作手册",
            "status": "pending",
            "required_fields": [
                "包含软件简介、运行环境、主要功能、操作流程、界面截图。",
                "截图需要覆盖核心页面与关键流程。",
                "说明书名称应与软件全称一致。",
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
                "申请人身份证明 / 营业执照",
                "委托代理材料（如有）",
                "合作开发协议 / 权属说明（如有多人或单位参与）",
            ],
            "notes": [
                "如果存在委托开发或合作开发，必须补齐权属归属说明。",
                "公司申请时需统一盖章信息与申请表主体名称。",
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


@register_feature_handler("software_copyright.copyright_materials")
async def build_copyright_materials(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate and persist a software copyright materials checklist."""
    params = context.params
    software_name = (
        str(params.get("software_name") or "").strip()
        or context.workspace_name
        or "待确认软件名称"
    )
    version = str(params.get("version") or params.get("software_version") or "V1.0").strip()
    applicant_name = str(params.get("applicant_name") or "待确认申请主体").strip()
    completion_date = str(params.get("completion_date") or "待确认开发完成日期").strip()
    highlights = _normalize_list(params.get("highlights"))
    target_platforms = _normalize_list(params.get("target_platforms"))
    source_modules = _normalize_list(params.get("source_modules"))

    await context.update(
        15,
        "梳理软著申请基础信息",
        current_step="collect",
        metadata={
            "software_name": software_name,
            "version": version,
        },
    )

    required_materials = _build_required_materials(
        software_name=software_name,
        version=version,
        applicant_name=applicant_name,
        completion_date=completion_date,
        highlights=highlights,
        target_platforms=target_platforms,
        source_modules=source_modules,
    )

    await context.update(
        55,
        "生成材料清单与核对项",
        current_step="organize",
        metadata={"materials_count": len(required_materials)},
    )

    artifact_title = f"{software_name} 软著申请材料清单"
    artifact_content = {
        "document_type": ArtifactType.COPYRIGHT_MATERIALS.value,
        "workspace": {
            "id": context.workspace_id,
            "name": context.workspace_name,
            "type": context.workspace_type,
            "discipline": context.workspace_discipline,
        },
        "software_profile": {
            "software_name": software_name,
            "version": version,
            "applicant_name": applicant_name,
            "completion_date": completion_date,
            "description": context.workspace_description,
            "config_snapshot": context.workspace_config,
        },
        "required_materials": required_materials,
        "review_checklist": [
            "软件名称、版本号、截图、说明书标题保持一致。",
            "源代码页码连续，避免只给零散代码片段。",
            "说明书截图覆盖登录、核心流程、结果页面与设置页面。",
            "申请主体、开发者、权利归属材料在申请表和附件中保持一致。",
        ],
        "next_actions": [
            "补齐基础信息后，先整理说明书目录与截图清单。",
            "从核心模块中截取连续代码页，优先选择最能体现原创性的部分。",
            "完成初稿后进行一次格式核对，再准备提交材料。",
        ],
    }

    artifacts = await context.persist_artifacts(
        [
            FeatureArtifactDraft(
                type=ArtifactType.COPYRIGHT_MATERIALS.value,
                title=artifact_title,
                content=artifact_content,
                created_by_skill=context.handler_key,
            )
        ]
    )

    await context.update(
        90,
        "已将材料清单保存到知识区",
        current_step="review",
        metadata={"artifact_ids": [artifact.id for artifact in artifacts]},
    )

    return WorkspaceFeatureExecutionResult(
        message=f"已生成《{artifact_title}》",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        next_steps=[
            "根据清单补齐申请表、说明书和连续代码页。",
            "如需进一步撰写说明书，可继续接入 technical_description handler。",
        ],
        data={
            "software_name": software_name,
            "version": version,
            "materials_count": len(required_materials),
        },
    )
