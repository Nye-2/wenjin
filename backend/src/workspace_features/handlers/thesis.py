"""Thesis workspace feature handlers (figure_generation, compile_export, opening_research).

These handlers implement workspace features that use task_type="workspace_feature"
and go through the standard handler registry, NOT the thesis LangGraph workflow.
"""

from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.runtime import (
    WorkspaceFeatureExecutionContext,
    register_feature_handler,
)


@register_feature_handler("thesis.figure_generation")
async def generate_figure(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate a figure based on description and type."""
    await context.update(10, "解析图表需求", current_step="plan")

    fig_type = context.params.get("type", "flowchart")
    description = context.params.get("description", "")
    chapter_index = context.params.get("chapter_index")

    await context.update(40, f"生成{fig_type}图表", current_step="generate")

    # TODO: 实际调用 ExecutionService 生成图表
    content = {
        "figure_type": fig_type,
        "description": description,
        "chapter_index": chapter_index,
        "render_data": {},  # placeholder for actual SVG/PNG data
    }

    artifact = FeatureArtifactDraft(
        type="figure",
        title=f"{context.workspace_name} - {description or '图表'}",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    await context.update(100, "图表生成完成", current_step="generate")

    return WorkspaceFeatureExecutionResult(
        message="图表已生成",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
    )


@register_feature_handler("thesis.compile_export")
async def compile_and_export(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Compile thesis LaTeX and generate PDF."""
    await context.update(10, "收集论文章节", current_step="assemble")

    template = context.params.get("template", "default")
    compiler = context.params.get("compiler", "xelatex")

    await context.update(40, "组装 LaTeX 文档", current_step="assemble")

    # TODO: 实际收集 artifacts 并组装 LaTeX
    content = {
        "template": template,
        "compiler": compiler,
        "latex_content": "",  # placeholder
        "pdf_path": "",  # placeholder
    }

    artifact = FeatureArtifactDraft(
        type="paper_draft",
        title=f"{context.workspace_name} - 编译稿",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    await context.update(100, "编译完成", current_step="compile")

    return WorkspaceFeatureExecutionResult(
        message="论文编译完成",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
    )


@register_feature_handler("thesis.opening_research")
async def opening_research(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate opening research report (开题报告/文献综述/可行性分析)."""
    await context.update(10, "分析研究主题", current_step="analyze")

    topic = context.params.get("topic", context.workspace_name)
    report_type = context.params.get("report_type", "opening_report")

    await context.update(40, "生成报告内容", current_step="generate")

    # TODO: 实际调用 LLM 生成报告内容
    content = {
        "topic": topic,
        "report_type": report_type,
        "workspace_description": context.workspace_description,
        "sections": [],  # placeholder
    }

    artifact = FeatureArtifactDraft(
        type=report_type,  # opening_report / literature_review / feasibility_analysis
        title=f"{context.workspace_name} - {_report_type_label(report_type)}",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    await context.update(100, "报告生成完成", current_step="generate")

    return WorkspaceFeatureExecutionResult(
        message=f"{_report_type_label(report_type)}已生成",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
    )


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")
