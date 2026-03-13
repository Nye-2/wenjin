"""Thesis workspace feature handlers.

These handlers implement workspace features that use task_type="workspace_feature"
and go through the standard handler registry, NOT the thesis LangGraph workflow.
"""

from src.artifacts import ArtifactType
from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.runtime import (
    WorkspaceFeatureExecutionContext,
    register_feature_handler,
)
from src.workspace_features.services import (
    build_compile_payload,
    build_figure_payload,
    build_literature_management_payload,
    build_opening_report_payload,
)


@register_feature_handler("thesis.figure_generation")
async def generate_figure(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate a figure based on description and type."""
    await context.update(10, "解析图表需求", current_step="plan")

    fig_type = context.params.get("type", "flowchart")
    description = context.params.get("description", "")
    chapter_index = _coerce_int(context.params.get("chapter_index"))

    await context.update(40, f"生成{fig_type}图表", current_step="generate")

    content = await build_figure_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        thread_id=context.thread_id,
        fig_type=str(fig_type),
        description=str(description),
        chapter_index=chapter_index,
    )

    artifact = FeatureArtifactDraft(
        type="figure",
        title=f"{context.workspace_name} - {description or '图表'}",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_status = str(content.get("status") or "unknown")
    await context.update(
        100,
        "图表生成完成" if generation_status == "generated" else "图表已降级保存，可后续升级渲染",
        current_step="generate",
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "图表已生成"
            if generation_status == "generated"
            else "图表执行能力暂不可用，已保存可执行源码/提示词，可后续自动升级"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "generation_status": generation_status,
            "strategy": content.get("strategy"),
            "upgrade": content.get("upgrade"),
        },
    )


@register_feature_handler("thesis.literature_management")
async def manage_literature(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate a structured literature inventory report for thesis workspace."""
    await context.update(10, "读取文献数据", current_step="scan")

    focus_topic = str(context.params.get("topic", context.workspace_name or "研究主题"))

    await context.update(40, "整理文献盘点报告", current_step="summarize")

    content = await build_literature_management_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        focus_topic=focus_topic,
    )

    summary = content.get("summary", {})
    total = int(summary.get("total", 0)) if isinstance(summary, dict) else 0
    core_count = int(summary.get("core_count", 0)) if isinstance(summary, dict) else 0

    artifact = FeatureArtifactDraft(
        type=ArtifactType.LITERATURE_INVENTORY.value,
        title=f"{context.workspace_name} - 文献管理盘点",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    await context.update(
        100,
        f"文献盘点完成（共 {total} 篇，核心 {core_count} 篇）",
        current_step="summarize",
        metadata={"total": total, "core_count": core_count},
    )

    return WorkspaceFeatureExecutionResult(
        message=f"文献管理盘点已生成（共 {total} 篇，核心 {core_count} 篇）",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={"total": total, "core_count": core_count},
    )


@register_feature_handler("thesis.compile_export")
async def compile_and_export(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Compile thesis LaTeX and generate PDF."""
    await context.update(10, "收集论文章节", current_step="assemble")

    template = context.params.get("template", "default")
    compiler = context.params.get("compiler", "xelatex")
    bibliography_style = context.params.get("bibliography_style", "gbt7714")

    await context.update(40, "组装 LaTeX 文档", current_step="assemble")

    content = await build_compile_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        workspace_description=context.workspace_description,
        thread_id=context.thread_id,
        template=str(template),
        compiler=str(compiler),
        bibliography_style=str(bibliography_style),
    )

    artifact = FeatureArtifactDraft(
        type="paper_draft",
        title=f"{context.workspace_name} - 编译稿",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    compile_status = str(content.get("compile_status") or "unknown")
    await context.update(
        100,
        "编译完成" if compile_status == "success" else "编译失败，已保存 LaTeX 草稿",
        current_step="compile",
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "论文编译完成"
            if compile_status == "success"
            else "论文草稿已生成，但编译失败，请检查日志后重试"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "compile_status": compile_status,
            "pdf_path": content.get("pdf_path"),
            "compile_error": content.get("compile_error"),
        },
    )


@register_feature_handler("thesis.opening_research")
async def opening_research(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate opening research report (开题报告/文献综述/可行性分析)."""
    await context.update(10, "分析研究主题", current_step="analyze")

    topic = context.params.get("topic", context.workspace_name)
    report_type = _normalize_report_type(str(context.params.get("report_type", "opening_report")))

    await context.update(40, "生成报告内容", current_step="generate")

    content = await build_opening_report_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        workspace_description=context.workspace_description,
        topic=str(topic),
        report_type=report_type,
        preferred_model=_read_optional_str(context.params.get("model_id")),
    )

    artifact = FeatureArtifactDraft(
        type=report_type,  # opening_report / literature_review / feasibility_analysis
        title=f"{context.workspace_name} - {_report_type_label(report_type)}",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    generation_mode = str(content.get("generation_mode") or "template_fallback")
    await context.update(
        100,
        "报告生成完成" if generation_mode == "llm" else "报告生成完成（模板降级）",
        current_step="generate",
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            f"{_report_type_label(report_type)}已生成"
            if generation_mode == "llm"
            else f"{_report_type_label(report_type)}已生成（模板模式）"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "generation_mode": generation_mode,
            "model_id": content.get("model_id"),
            "generation_error": content.get("generation_error"),
        },
    )


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")


def _normalize_report_type(report_type: str) -> str:
    return {
        "opening_report": "opening_report",
        "literature_review": "literature_review",
        "feasibility_analysis": "feasibility_analysis",
    }.get(report_type, "opening_report")


def _coerce_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
