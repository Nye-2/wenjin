"""Proposal workspace feature handlers (proposal_outline, background_research).

These handlers implement workspace features that use task_type="workspace_feature"
and go through the standard handler registry.
"""

from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.runtime import (
    WorkspaceFeatureExecutionContext,
    register_feature_handler,
)
from src.workspace_features.services.proposal_feature_service import (
    build_background_research_payload,
    build_proposal_outline_payload,
)


def _read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@register_feature_handler("proposal.proposal_outline")
async def generate_proposal_outline(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate proposal outline with sections, milestones, and risks."""
    await context.update(10, "分析申报需求", current_step="analyze")

    topic = context.params.get("topic", context.workspace_name)
    proposal_type = str(context.params.get("proposal_type", "other"))
    period_months = _read_optional_int(context.params.get("period_months"))
    preferred_model = _read_optional_str(context.params.get("model_id"))

    await context.update(40, "生成申报书大纲", current_step="generate")

    content = await build_proposal_outline_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        topic=str(topic),
        proposal_type=proposal_type,
        period_months=period_months,
        preferred_model=preferred_model,
    )

    artifact = FeatureArtifactDraft(
        type="proposal",
        title=f"{context.workspace_name} - 申报书大纲",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_mode = str(content.get("generation_mode") or "template_fallback")
    await context.update(
        100,
        "申报书大纲生成完成" if generation_mode == "llm" else "申报书大纲生成完成（模板模式）",
        current_step="generate",
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "申报书大纲已生成"
            if generation_mode == "llm"
            else "申报书大纲已生成（模板模式），可手动编辑完善"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "generation_mode": generation_mode,
            "model_id": content.get("model_id"),
            "proposal_type": content.get("proposal_type"),
            "period_months": content.get("period_months"),
            "generation_error": content.get("generation_error"),
        },
    )


@register_feature_handler("proposal.background_research")
async def conduct_background_research(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Conduct background research with status overview, problems, and directions."""
    await context.update(10, "分析调研主题", current_step="analyze")

    keywords = context.params.get("keywords", context.workspace_name)
    industry_scope = str(context.params.get("industry_scope", "相关领域"))
    time_range = str(context.params.get("time_range", "近5年"))
    preferred_model = _read_optional_str(context.params.get("model_id"))

    await context.update(40, "生成背景调研报告", current_step="generate")

    content = await build_background_research_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        keywords=str(keywords),
        industry_scope=industry_scope,
        time_range=time_range,
        preferred_model=preferred_model,
    )

    artifact = FeatureArtifactDraft(
        type="background_research",
        title=f"{context.workspace_name} - 背景调研",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_mode = str(content.get("generation_mode") or "template_fallback")
    await context.update(
        100,
        "背景调研完成" if generation_mode == "llm" else "背景调研完成（模板模式）",
        current_step="generate",
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "背景调研报告已生成"
            if generation_mode == "llm"
            else "背景调研报告已生成（模板模式），可手动编辑完善"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "generation_mode": generation_mode,
            "model_id": content.get("model_id"),
            "keywords": content.get("keywords"),
            "generation_error": content.get("generation_error"),
        },
    )
