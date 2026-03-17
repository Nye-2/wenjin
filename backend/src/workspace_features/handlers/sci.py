"""SCI workspace feature handlers (literature_search, paper_analysis, writing)."""

from src.artifacts import ArtifactType
from src.workspace_features.contracts import (
    FeatureArtifactDraft,
    WorkspaceFeatureExecutionResult,
)
from src.workspace_features.runtime import (
    WorkspaceFeatureExecutionContext,
    register_feature_handler,
)
from src.workspace_features.services.sci_feature_service import (
    build_literature_search_payload,
    build_paper_analysis_payload,
    build_sci_writing_payload,
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


def _normalize_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
        return [item for item in items if item]
    return []


@register_feature_handler("sci.literature_search")
async def search_literature(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate literature search result payload and persist artifact."""
    await context.update(10, "解析检索需求", current_step="search")

    query = str(
        context.params.get("query")
        or context.params.get("keywords")
        or context.workspace_description
        or context.workspace_name
        or "研究主题"
    ).strip()
    discipline = (
        str(context.params.get("discipline") or context.workspace_discipline).strip()
        or None
    )
    preferred_model = _read_optional_str(context.params.get("model_id"))

    await context.update(45, "生成文献检索结果", current_step="filter")

    content = await build_literature_search_payload(
        workspace_id=context.workspace_id,
        query=query,
        discipline=discipline,
        preferred_model=preferred_model,
    )

    artifact = FeatureArtifactDraft(
        type=ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        title=f"{context.workspace_name} - 文献检索结果",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    papers = content.get("papers", [])
    top_hits = content.get("top_hits", [])
    generation_mode = str(content.get("search_strategy") or "template_fallback")

    await context.update(
        100,
        "文献检索完成" if generation_mode == "llm_synthesis" else "文献检索完成（模板模式）",
        current_step="filter",
        metadata={
            "results_count": len(papers) if isinstance(papers, list) else 0,
            "top_hits_count": len(top_hits) if isinstance(top_hits, list) else 0,
            "generation_mode": generation_mode,
        },
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "文献检索已完成"
            if generation_mode == "llm_synthesis"
            else "文献检索已完成（模板模式），可补充真实检索结果"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "query": content.get("query"),
            "generation_mode": generation_mode,
            "results_count": len(papers) if isinstance(papers, list) else 0,
            "top_hits_count": len(top_hits) if isinstance(top_hits, list) else 0,
            "model_id": content.get("model_id"),
            "generation_error": content.get("generation_error"),
        },
    )


@register_feature_handler("sci.paper_analysis")
async def analyze_paper(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate paper analysis payload and persist artifact."""
    await context.update(10, "解析论文信息", current_step="parse")

    paper_id = _read_optional_str(context.params.get("paper_id"))
    paper_title = (
        _read_optional_str(context.params.get("paper_title"))
        or _read_optional_str(context.params.get("title"))
        or "未命名论文"
    )
    paper_abstract = _read_optional_str(context.params.get("paper_abstract"))
    preferred_model = _read_optional_str(context.params.get("model_id"))

    await context.update(45, "生成论文结构化分析", current_step="analyze")

    content = await build_paper_analysis_payload(
        workspace_id=context.workspace_id,
        paper_id=paper_id,
        paper_title=paper_title,
        paper_abstract=paper_abstract,
        preferred_model=preferred_model,
    )

    artifact = FeatureArtifactDraft(
        type=ArtifactType.PAPER_ANALYSIS.value,
        title=f"{context.workspace_name} - 论文分析",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    analysis_mode = str(content.get("analysis_mode") or "template_fallback")
    sections = content.get("sections")
    section_count = len(sections) if isinstance(sections, dict) else 0

    await context.update(
        100,
        "论文分析完成" if analysis_mode == "llm" else "论文分析完成（模板模式）",
        current_step="summarize",
        metadata={
            "analysis_mode": analysis_mode,
            "section_count": section_count,
        },
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "论文分析已完成"
            if analysis_mode == "llm"
            else "论文分析已完成（模板模式），可继续补充细化"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "paper_id": content.get("paper_id"),
            "paper_title": content.get("paper_title"),
            "analysis_mode": analysis_mode,
            "section_count": section_count,
            "model_id": content.get("model_id"),
            "generation_error": content.get("generation_error"),
        },
    )


@register_feature_handler("sci.writing")
async def write_sci_paper(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    """Generate SCI section draft and persist as paper_draft artifact."""
    await context.update(10, "解析写作需求", current_step="plan")

    paper_title = (
        _read_optional_str(context.params.get("paper_title"))
        or _read_optional_str(context.params.get("title"))
        or context.workspace_name
        or "未命名论文"
    )
    section_type = (
        _read_optional_str(context.params.get("section_type"))
        or _read_optional_str(context.params.get("section"))
        or "introduction"
    )
    target_words = _read_optional_int(context.params.get("target_words")) or 1200
    context_artifact_ids = _normalize_str_list(context.params.get("context_artifact_ids"))
    preferred_model = _read_optional_str(context.params.get("model_id"))

    await context.update(45, "生成论文章节草稿", current_step="write")

    content = await build_sci_writing_payload(
        workspace_id=context.workspace_id,
        workspace_name=context.workspace_name,
        workspace_description=context.workspace_description,
        paper_title=paper_title,
        section_type=section_type,
        target_words=target_words,
        context_artifact_ids=context_artifact_ids,
        preferred_model=preferred_model,
    )

    section_title = (
        _read_optional_str(content.get("section_title"))
        or _read_optional_str(content.get("section_type"))
        or "Section"
    )
    artifact = FeatureArtifactDraft(
        type=ArtifactType.PAPER_DRAFT.value,
        title=f"{paper_title} - {section_title} draft",
        content=content,
        created_by_skill=context.handler_key,
    )
    artifacts = await context.persist_artifacts([artifact])

    writing_mode = str(content.get("writing_mode") or "template_fallback")
    raw_word_count = content.get("word_count")
    word_count = raw_word_count if isinstance(raw_word_count, int) else 0

    await context.update(
        100,
        "论文写作完成" if writing_mode == "llm" else "论文写作完成（模板模式）",
        current_step="revise",
        metadata={
            "writing_mode": writing_mode,
            "section_type": content.get("section_type"),
            "word_count": word_count,
            "output_language": content.get("output_language"),
        },
    )

    return WorkspaceFeatureExecutionResult(
        message=(
            "论文草稿已生成"
            if writing_mode == "llm"
            else "论文草稿已生成（模板模式），可继续编辑完善"
        ),
        artifacts=artifacts,
        refresh_targets=["artifacts"],
        data={
            "paper_title": content.get("paper_title"),
            "section_type": content.get("section_type"),
            "section_title": content.get("section_title"),
            "writing_mode": writing_mode,
            "word_count": word_count,
            "target_words": content.get("target_words"),
            "output_language": content.get("output_language"),
            "model_id": content.get("model_id"),
            "generation_error": content.get("generation_error"),
        },
    )
