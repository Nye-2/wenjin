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
from src.task.progress import ProgressTracker
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

    try:
        await progress.update(5, "启动 LangGraph 增强处理")
        result = await execute_feature_graph(
            workspace_type,
            feature_id,
            payload,
            user_id=str(user_id) if user_id else None,
        )
        artifacts = await _persist_langgraph_artifacts(
            feature_id, workspace_type, payload, result
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
            from src.agents.middleware.memory import extract_and_persist_knowledge

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
