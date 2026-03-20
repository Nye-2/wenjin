"""Unified workspace feature execution handler.

All workspace types now route through workspace_lead_agent.execute_feature_graph.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts.types import ArtifactType
from src.database import get_db_session
from src.task.progress import (
    ProgressTracker,
    bind_progress_tracker,
    bind_runtime_state,
    reset_progress_tracker,
    reset_runtime_state,
)
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    create_feature_runtime,
    runtime_progress_for_phase,
    upsert_runtime_block,
)
from src.workspace_features import get_workspace_feature

logger = logging.getLogger(__name__)

_THESIS_WRITING_LANGGRAPH_ACTIONS = {
    "generate_outline",
    "write_chapter",
    "review_section",
    "revise_section",
    "review_and_revise",
}


def _read_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    return params if isinstance(params, dict) else {}


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")


def _build_langgraph_artifact_drafts(
    feature_id: str,
    workspace_name: str,
    workspace_type: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map LangGraph feature result to artifact drafts."""
    title_prefix = workspace_name or "未命名工作区"

    # Thesis workspace artifacts
    if workspace_type == "thesis":
        if feature_id == "literature_management":
            return [
                {
                    "type": ArtifactType.LITERATURE_INVENTORY.value,
                    "title": f"{title_prefix} - 文献管理盘点",
                    "content": result,
                }
            ]
        if feature_id == "opening_research":
            report_type = str(result.get("report_type", "opening_report"))
            return [
                {
                    "type": report_type,
                    "title": f"{title_prefix} - {_report_type_label(report_type)}",
                    "content": result,
                }
            ]
        if feature_id == "figure_generation":
            description = str(result.get("description") or "图表")
            return [
                {
                    "type": ArtifactType.FIGURE.value,
                    "title": f"{title_prefix} - {description}",
                    "content": result,
                }
            ]
        if feature_id == "compile_export":
            return [
                {
                    "type": ArtifactType.PAPER_DRAFT.value,
                    "title": f"{title_prefix} - 编译预检结果",
                    "content": result,
                }
            ]
        if feature_id == "deep_research":
            topic = str(result.get("topic") or title_prefix)
            drafts: list[dict[str, Any]] = []
            discovery = result.get("discovery")
            if isinstance(discovery, dict) and discovery:
                drafts.append(
                    {
                        "type": ArtifactType.LITERATURE_REVIEW.value,
                        "title": f"{topic} - 深度调研综述",
                        "content": {
                            "topic": topic,
                            "discovery": discovery,
                            "cross_validation": result.get("cross_validation"),
                            "generation_mode": result.get("generation_mode"),
                        },
                    }
                )
            return drafts
        if feature_id == "thesis_writing":
            action = str(result.get("action") or "").strip().lower()

            if action == "generate_outline":
                outline = result.get("outline")
                if not isinstance(outline, dict) or not outline:
                    return []

                return [
                    {
                        "type": ArtifactType.FRAMEWORK_OUTLINE.value,
                        "title": f"{title_prefix} - 论文大纲",
                        "content": {
                            "paper_title": str(result.get("paper_title") or title_prefix),
                            "outline": outline,
                            "source_context": (
                                result.get("source_context")
                                if isinstance(result.get("source_context"), dict)
                                else {}
                            ),
                            "generation_mode": result.get("generation_mode"),
                            "model_id": result.get("model_id"),
                            "schema_version": result.get("schema_version"),
                        },
                    }
                ]

            if action == "write_chapter":
                chapter = result.get("chapter")
                if not isinstance(chapter, dict) or not chapter:
                    return []

                chapter_content = dict(chapter)
                chapter_content.setdefault("model_id", result.get("model_id"))
                chapter_content.setdefault(
                    "generation_mode",
                    result.get("generation_mode"),
                )

                chapter_title = str(
                    chapter.get("chapter_title")
                    or chapter.get("title")
                    or "章节草稿"
                )
                return [
                    {
                        "type": ArtifactType.THESIS_CHAPTER.value,
                        "title": f"{title_prefix} - {chapter_title}",
                        "content": chapter_content,
                    }
                ]

            return []

    # SCI workspace artifacts
    if workspace_type == "sci":
        if feature_id == "literature_search":
            return [
                {
                    "type": ArtifactType.LITERATURE_SEARCH_RESULTS.value,
                    "title": f"{title_prefix} - Literature Search",
                    "content": result,
                }
            ]
        if feature_id == "paper_analysis":
            return [
                {
                    "type": ArtifactType.PAPER_ANALYSIS.value,
                    "title": f"{title_prefix} - Paper Analysis",
                    "content": result,
                }
            ]
        if feature_id == "writing":
            return [
                {
                    "type": ArtifactType.PAPER_DRAFT.value,
                    "title": f"{title_prefix} - {result.get('section_type', 'Section')}",
                    "content": result,
                }
            ]

    # Patent workspace artifacts
    if workspace_type == "patent":
        if feature_id == "patent_outline":
            return [
                {
                    "type": ArtifactType.PATENT_OUTLINE.value,
                    "title": f"{title_prefix} - 专利说明书框架",
                    "content": result,
                }
            ]
        if feature_id == "prior_art_search":
            return [
                {
                    "type": ArtifactType.PRIOR_ART_REPORT.value,
                    "title": f"{title_prefix} - 现有技术分析",
                    "content": result,
                }
            ]

    # Proposal workspace artifacts
    if workspace_type == "proposal":
        if feature_id == "proposal_outline":
            return [
                {
                    "type": ArtifactType.PROPOSAL.value,
                    "title": f"{title_prefix} - 申报书大纲",
                    "content": result,
                }
            ]
        if feature_id == "background_research":
            return [
                {
                    "type": ArtifactType.BACKGROUND_RESEARCH.value,
                    "title": f"{title_prefix} - 背景调研报告",
                    "content": result,
                }
            ]

    # Software copyright workspace artifacts
    if workspace_type == "software_copyright":
        if feature_id == "copyright_materials":
            return [
                {
                    "type": ArtifactType.COPYRIGHT_MATERIALS.value,
                    "title": f"{result.get('software_profile', {}).get('software_name', title_prefix)} 软著申请材料清单",
                    "content": result,
                }
            ]
        if feature_id == "technical_description":
            return [
                {
                    "type": ArtifactType.TECHNICAL_DESCRIPTION.value,
                    "title": f"{title_prefix} - 技术说明书",
                    "content": result,
                }
            ]

    return []


async def _persist_langgraph_artifacts(
    feature_id: str,
    workspace_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Persist artifacts for LangGraph feature results."""
    workspace_id = str(payload.get("workspace_id") or "")
    if not workspace_id:
        return []

    drafts = _build_langgraph_artifact_drafts(
        feature_id,
        str(payload.get("workspace_name") or ""),
        workspace_type,
        result,
    )
    if not drafts:
        return []

    created_by_skill = str(payload.get("handler_key") or f"{workspace_type}.{feature_id}")
    try:
        async with get_db_session() as db:
            service = ArtifactService(db)
            refs: list[dict[str, str]] = []
            for draft in drafts:
                artifact = await service.create(
                    workspace_id=workspace_id,
                    type=str(draft["type"]),
                    title=str(draft["title"]),
                    content=draft["content"],
                    created_by_skill=created_by_skill,
                )
                refs.append(
                    {
                        "id": str(artifact.id),
                        "type": artifact.type,
                        "title": artifact.title or "",
                    }
                )
            return refs
    except Exception:
        logger.warning(
            "Failed to persist LangGraph artifacts for feature '%s'",
            feature_id,
            exc_info=True,
        )
        return []


async def _try_langgraph_execution(
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any] | None:
    """Attempt LangGraph sub-graph execution. Returns None on failure."""
    from src.agents.workspace_lead_agent import execute_feature_graph

    user_id = payload.get("user_id") or payload.get("created_by")
    params = _read_params(payload)

    if feature_id == "literature_search":
        runtime = create_feature_runtime(
            feature_id,
            [
                {"label": "关键词", "value": str(params.get("query") or payload.get("workspace_name") or "未指定")},
                {"label": "学科", "value": str(params.get("discipline") or payload.get("workspace_discipline") or "未指定")},
            ],
        )
    elif feature_id == "paper_analysis":
        runtime = create_feature_runtime(
            feature_id,
            [
                {"label": "论文标题", "value": str(params.get("paper_title") or payload.get("workspace_name") or "未命名论文")},
                {"label": "Paper ID", "value": str(params.get("paper_id") or "未提供")},
            ],
        )
    elif feature_id == "writing":
        runtime = create_feature_runtime(
            feature_id,
            [
                {"label": "标题", "value": str(params.get("paper_title") or payload.get("workspace_name") or "未命名论文")},
                {"label": "章节", "value": str(params.get("section_type") or "introduction")},
                {"label": "目标字数", "value": str(params.get("target_words") or 1200)},
            ],
        )
    elif feature_id == "opening_research":
        runtime = create_feature_runtime(
            feature_id,
            [
                {"label": "主题", "value": str(params.get("topic") or payload.get("workspace_name") or "未指定主题")},
                {"label": "报告类型", "value": str(params.get("report_type") or "opening_report")},
            ],
        )
    elif feature_id == "background_research":
        runtime = create_feature_runtime(
            feature_id,
            [
                {"label": "关键词", "value": str(params.get("keywords") or payload.get("workspace_name") or "未指定主题")},
                {"label": "行业范围", "value": str(params.get("industry_scope") or "相关领域")},
                {"label": "时间范围", "value": str(params.get("time_range") or "近5年")},
            ],
        )
    else:
        runtime = None

    try:
        if runtime is not None:
            append_runtime_activity(
                runtime,
                title="任务启动",
                description="正在准备参数并启动增强执行。",
            )
            await progress.update(
                8,
                "启动 LangGraph 增强处理",
                current_step=runtime.get("current_phase"),
                metadata={"runtime": runtime},
                stage_transition=True,
            )
        else:
            await progress.update(5, "启动 LangGraph 增强处理")

        progress_token = bind_progress_tracker(progress)
        runtime_token = bind_runtime_state(runtime) if runtime is not None else None
        try:
            result = await execute_feature_graph(
                workspace_type,
                feature_id,
                payload,
                user_id=str(user_id) if user_id else None,
            )
        finally:
            reset_progress_tracker(progress_token)
            if runtime_token is not None:
                reset_runtime_state(runtime_token)
        artifacts = await _persist_langgraph_artifacts(
            feature_id, workspace_type, payload, result
        )

        if runtime is not None:
            current_phase = runtime.get("current_phase")
            if current_phase:
                advance_runtime_phase(runtime, str(current_phase), None)
            if feature_id in {"literature_search", "paper_analysis", "writing", "opening_research", "background_research"}:
                append_runtime_activity(
                    runtime,
                    title="结果已整理",
                    description=f"{feature_id} 已完成结构化输出并写入 artifact。",
                    tone="success",
                )
                result_metrics = [
                    {"label": "生成模式", "value": str(result.get("generation_mode") or "unknown")},
                    {"label": "Artifact", "value": str(len(artifacts))},
                ]
                if feature_id == "literature_search":
                    top_hits = result.get("top_hits")
                    result_metrics.insert(1, {"label": "Top Hits", "value": str(len(top_hits) if isinstance(top_hits, list) else 0)})
                    upsert_runtime_block(
                        runtime,
                        {
                            "id": "search-results",
                            "kind": "list",
                            "title": "高相关命中",
                            "description": "优先推荐的文献候选",
                            "items": [
                                {
                                    "title": str(item.get("title") or "Untitled"),
                                    "description": str(item.get("summary") or ""),
                                    "meta": str(item.get("venue") or ""),
                                    "badge": str(item.get("year") or "") or None,
                                }
                                for item in (top_hits or [])[:5]
                                if isinstance(item, dict)
                            ],
                        },
                    )
                elif feature_id == "paper_analysis":
                    sections = result.get("sections")
                    upsert_runtime_block(
                        runtime,
                        {
                            "id": "analysis-sections",
                            "kind": "list",
                            "title": "分析分区",
                            "description": "方法、实验、结论与创新点",
                            "items": [
                                {
                                    "title": str(section.get("title") or key),
                                    "description": str(section.get("content") or "")[:220],
                                    "meta": (
                                        f"{len(section.get('key_points', []))} 个要点"
                                        if isinstance(section.get("key_points"), list)
                                        else ""
                                    ),
                                }
                                for key, section in (sections or {}).items()
                                if isinstance(section, dict)
                            ],
                        },
                    )
                elif feature_id == "writing":
                    upsert_runtime_block(
                        runtime,
                        {
                            "id": "draft-preview",
                            "kind": "text",
                            "title": "草稿预览",
                            "description": str(result.get("section_title") or result.get("section_type") or "章节草稿"),
                            "content": str(result.get("content") or "")[:1200],
                        },
                    )
                    references = result.get("references")
                    if isinstance(references, list):
                        upsert_runtime_block(
                            runtime,
                            {
                                "id": "references",
                                "kind": "list",
                                "title": "参考建议",
                                "items": [
                                    {"title": str(reference), "description": ""}
                                    for reference in references[:6]
                                ],
                            },
                        )
                elif feature_id in {"opening_research", "background_research"}:
                    sections = result.get("sections")
                    upsert_runtime_block(
                        runtime,
                        {
                            "id": "sections",
                            "kind": "list",
                            "title": "报告章节",
                            "description": "已生成的结构化章节内容",
                            "items": [
                                {
                                    "title": str(section.get("title") or "未命名章节"),
                                    "description": str(section.get("content") or "")[:220],
                                    "meta": str(section.get("source") or ""),
                                }
                                for section in (sections or [])[:6]
                                if isinstance(section, dict)
                            ],
                        },
                    )
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "result-summary",
                        "kind": "metrics",
                        "title": "输出概览",
                        "entries": result_metrics,
                    },
                )

        # Wrap result in standard feature response format
        wrapped = {
            "success": True,
            "feature_id": feature_id,
            "feature_name": payload.get("feature_name", feature_id),
            "workspace_type": workspace_type,
            "handler_key": payload.get("handler_key", f"{workspace_type}.{feature_id}"),
            "generation_mode": result.get("generation_mode", "llm"),
            "message": f"{feature_id} 已通过 LangGraph 增强完成",
            "data": result,
            "artifacts": artifacts,
            "refresh_targets": ["artifacts"],
            "generated_at": result.get("generated_at", datetime.now(tz=UTC).isoformat()),
        }
        if runtime is not None:
            wrapped["runtime"] = runtime
            await progress.update(
                max(runtime_progress_for_phase(runtime), 98),
                "LangGraph 增强处理完成",
                current_step=runtime.get("current_phase"),
                metadata={"runtime": runtime},
                stage_transition=True,
            )
        else:
            await progress.update(100, "LangGraph 增强处理完成")
        return wrapped
    except Exception:
        logger.warning(
            "LangGraph execution failed for feature '%s' in workspace '%s'",
            feature_id,
            workspace_type,
            exc_info=True,
        )
        return None


def _schedule_memory_extraction(
    workspace_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Schedule async memory extraction (fire-and-forget)."""
    user_id = payload.get("user_id") or payload.get("created_by")
    if not user_id:
        return

    workspace_id = payload.get("workspace_id")
    feature_id = payload.get("feature_id", "")

    summary_parts = [
        f"Workspace: {workspace_type}",
        f"Feature: {feature_id}",
        f"Result mode: {result.get('generation_mode', 'unknown')}",
    ]
    message = result.get("message", "")
    if message:
        summary_parts.append(f"Output: {message}")

    conversation_text = "; ".join(summary_parts)

    async def _extract():
        try:
            from src.agents.middlewares.memory import extract_and_persist_knowledge

            await extract_and_persist_knowledge(
                str(user_id),
                conversation_text,
                workspace_context=str(workspace_id) if workspace_id else None,
                source=f"feature:{workspace_type}.{feature_id}",
            )
        except Exception:
            logger.debug("Memory extraction failed for feature %s", feature_id, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_extract())
    except RuntimeError:
        pass


async def execute_workspace_feature(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute a workspace feature using LangGraph sub-graphs.

    All workspace types now route through workspace_lead_agent.execute_feature_graph.
    """
    workspace_type = str(payload.get("workspace_type") or "")
    feature_id = str(payload.get("feature_id") or "")

    # Validate feature exists in registry
    feature = get_workspace_feature(workspace_type, feature_id)
    if not feature:
        raise ValueError(
            f"Unknown workspace feature '{feature_id}' for workspace type '{workspace_type}'"
        )

    # Try LangGraph sub-graph execution
    result = await _try_langgraph_execution(workspace_type, feature_id, payload, progress)

    if result is not None:
        _schedule_memory_extraction(workspace_type, payload, result)
        return result

    # If LangGraph failed, raise error (no fallback to handler per handoff doc)
    raise RuntimeError(
        f"LangGraph execution failed for feature '{feature_id}' in workspace '{workspace_type}'"
    )


# Thesis writing actions that route to thesis_writing LangGraph sub-graph
async def execute_thesis_generation(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute thesis generation - routes through LangGraph."""
    params = _read_params(payload)
    action = payload.get("action") or params.get("action", "write_all")

    # Thesis-writing actions route to thesis_writing LangGraph sub-graph.
    if str(action) in _THESIS_WRITING_LANGGRAPH_ACTIONS:
        result = await _try_langgraph_execution(
            "thesis", "thesis_writing", payload, progress
        )
        if result is not None:
            _schedule_memory_extraction("thesis", payload, result)
            return result

    # Default: route through feature registry
    return await execute_workspace_feature(payload, progress)
