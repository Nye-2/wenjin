"""Patent workspace feature handlers (patent_outline, prior_art_search).

These handlers implement workspace features that use task_type="workspace_feature"
and go through the standard handler registry.
"""

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
from src.workspace_features.services.patent_feature_service import (
    build_patent_outline_payload,
    build_prior_art_search_payload,
)


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


@register_feature_handler("patent.patent_outline")
async def generate_patent_outline(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate patent specification outline and claims draft."""
    await context.update(10, "解析创新点信息", current_step="analyze")

    params = context.params
    innovation_description = _normalize_text(
        params.get("innovation_description"),
        context.workspace_description or context.workspace_name,
    )
    technical_field = _normalize_text(params.get("technical_field"))
    application_scenario = _normalize_text(params.get("application_scenario"))
    implementation_method = _normalize_text(params.get("implementation_method"))
    preferred_model = _normalize_text(params.get("model_id")) or None

    await context.update(40, "生成专利说明书框架", current_step="structure")

    content = await build_patent_outline_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        workspace_description=context.workspace_description,
        innovation_description=innovation_description,
        technical_field=technical_field,
        application_scenario=application_scenario,
        implementation_method=implementation_method,
        preferred_model=preferred_model,
    )

    artifact_title = f"{context.workspace_name} - 专利说明书框架"
    artifact = FeatureArtifactDraft(
        type=ArtifactType.PATENT_OUTLINE.value,
        title=artifact_title,
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_mode = str(content.get("generation_mode") or "template_fallback")
    evidence_points = content.get("evidence_points_needed", [])
    await context.update(
        100,
        "专利框架生成完成" if generation_mode == "llm" else "专利框架已生成（模板模式）",
        current_step="refine",
        metadata={
            "generation_mode": generation_mode,
            "evidence_points_count": len(evidence_points),
        },
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            f"专利说明书框架已生成，包含{len(content.get('sections', []))}个章节"
            if generation_mode == "llm"
            else f"专利说明书框架已生成（模板模式），请补充{len(evidence_points)}个待补证据点"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        next_steps=[
            "根据生成的框架补充技术细节",
            "完善权利要求书的具体内容",
            "准备附图及说明",
        ] if generation_mode == "llm" else [
            f"补充以下待补证据点：{', '.join(evidence_points[:3])}...",
            "完善各章节的具体技术内容",
            "细化权利要求书",
        ],
        data={
            "generation_mode": generation_mode,
            "output_language": content.get("output_language"),
            "sections_count": len(content.get("sections", [])),
            "claims_count": len(content.get("claims_draft", {}).get("independent_claims", []))
            + len(content.get("claims_draft", {}).get("dependent_claims", [])),
            "evidence_points_needed": evidence_points,
        },
    )


@register_feature_handler("patent.prior_art_search")
async def search_prior_art(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Search and analyze prior art for novelty assessment."""
    await context.update(10, "解析检索条件", current_step="search")

    params = context.params
    keywords = _normalize_list(params.get("keywords"))
    ipc_codes = _normalize_list(params.get("ipc_codes"))
    time_range = _normalize_text(params.get("time_range"), "近5年")
    preferred_model = _normalize_text(params.get("model_id")) or None

    await context.update(40, "分析现有技术对比", current_step="compare")

    content = await build_prior_art_search_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        workspace_description=context.workspace_description,
        keywords=keywords,
        ipc_codes=ipc_codes,
        time_range=time_range,
        preferred_model=preferred_model,
    )

    artifact_title = f"{context.workspace_name} - 现有技术检索报告"
    artifact = FeatureArtifactDraft(
        type=ArtifactType.PRIOR_ART_REPORT.value,
        title=artifact_title,
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_mode = str(content.get("generation_mode") or "template_fallback")
    risks = content.get("novelty_risks", [])
    high_risks = [r for r in risks if r.get("level") == "high"]
    suggestions = content.get("avoidance_suggestions", [])

    await context.update(
        100,
        "现有技术检索分析完成" if generation_mode == "llm" else "检索报告已生成（模板模式）",
        current_step="compare",
        metadata={
            "generation_mode": generation_mode,
            "risks_count": len(risks),
            "high_risks_count": len(high_risks),
        },
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            f"现有技术检索报告已生成，发现{len(risks)}个新颖性风险点"
            if generation_mode == "llm"
            else "检索报告框架已生成，请补充具体检索结果"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        next_steps=[
            "查看对比表，了解相关专利",
            "针对高风险点调整权利要求",
            "参考规避建议优化技术方案",
        ] if generation_mode == "llm" else [
            "使用检索关键词在专利数据库中检索",
            "将检索结果填入对比表",
            "评估新颖性风险",
        ],
        data={
            "generation_mode": generation_mode,
            "output_language": content.get("output_language"),
            "keywords": content.get("keywords", []),
            "ipc_codes": content.get("ipc_codes", []),
            "time_range": content.get("time_range"),
            "comparison_count": len(content.get("comparison_table", [])),
            "risks_count": len(risks),
            "high_risks_count": len(high_risks),
            "suggestions_count": len(suggestions),
        },
    )
