"""Artifact mapping and persistence helpers for workspace feature execution."""

from __future__ import annotations

import logging
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts.types import ArtifactType
from src.database import get_db_session

logger = logging.getLogger(__name__)


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")


def build_langgraph_artifact_drafts(
    feature_id: str,
    workspace_name: str,
    workspace_type: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map LangGraph feature result to artifact drafts."""
    title_prefix = workspace_name or "未命名工作区"

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
            discovery = result.get("discovery")
            return [
                {
                    "type": ArtifactType.DEEP_RESEARCH_REPORT.value,
                    "title": f"{topic} - 深度调研报告",
                    "content": {
                        "schema_version": str(result.get("schema_version") or "v1"),
                        "source_feature": str(
                            result.get("source_feature") or "deep_research"
                        ),
                        "topic": topic,
                        "discipline": result.get("discipline"),
                        "query": (
                            result.get("query")
                            if isinstance(result.get("query"), dict)
                            else {"keywords": [topic], "constraints": []}
                        ),
                        "corpus": (
                            result.get("corpus")
                            if isinstance(result.get("corpus"), dict)
                            else {}
                        ),
                        "discovery": discovery if isinstance(discovery, dict) else {},
                        "gaps": (
                            result.get("gaps")
                            if isinstance(result.get("gaps"), list)
                            else []
                        ),
                        "ideas": (
                            result.get("ideas")
                            if isinstance(result.get("ideas"), list)
                            else []
                        ),
                        "recommended_actions": (
                            result.get("recommended_actions")
                            if isinstance(result.get("recommended_actions"), list)
                            else []
                        ),
                        "cross_validation": result.get("cross_validation"),
                        "model_id": result.get("model_id"),
                        "pipeline_steps": result.get("pipeline_steps"),
                        "generation_mode": result.get("generation_mode"),
                        "generated_at": result.get("generated_at"),
                    },
                }
            ]
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
                    chapter.get("chapter_title") or chapter.get("title") or "章节草稿"
                )
                return [
                    {
                        "type": ArtifactType.THESIS_CHAPTER.value,
                        "title": f"{title_prefix} - {chapter_title}",
                        "content": chapter_content,
                    }
                ]

            if action == "write_all":
                drafts: list[dict[str, Any]] = []

                outline = result.get("outline")
                if isinstance(outline, dict) and outline:
                    drafts.append(
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
                    )

                chapters = result.get("chapters")
                if isinstance(chapters, list):
                    for index, chapter in enumerate(chapters, start=1):
                        if not isinstance(chapter, dict):
                            continue
                        chapter_content = dict(chapter)
                        chapter_content.setdefault("model_id", result.get("model_id"))
                        chapter_content.setdefault(
                            "generation_mode",
                            result.get("generation_mode"),
                        )
                        chapter_title = str(
                            chapter.get("chapter_title")
                            or chapter.get("title")
                            or f"章节草稿 {index}"
                        )
                        drafts.append(
                            {
                                "type": ArtifactType.THESIS_CHAPTER.value,
                                "title": f"{title_prefix} - {chapter_title}",
                                "content": chapter_content,
                            }
                        )
                return drafts

            return []

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
            section_label = str(
                result.get("section_title")
                or result.get("section_type")
                or "Section"
            ).strip() or "Section"
            return [
                {
                    "type": ArtifactType.PAPER_DRAFT.value,
                    "title": f"{title_prefix} - {section_label}",
                    "content": result,
                }
            ]
        if feature_id == "literature_review":
            return [
                {
                    "type": ArtifactType.LITERATURE_REVIEW.value,
                    "title": f"{title_prefix} - Literature Review",
                    "content": result,
                }
            ]
        if feature_id == "framework_outline":
            return [
                {
                    "type": ArtifactType.FRAMEWORK_OUTLINE.value,
                    "title": f"{title_prefix} - Framework Outline",
                    "content": result,
                }
            ]
        if feature_id == "peer_review":
            return [
                {
                    "type": ArtifactType.REVIEW.value,
                    "title": f"{title_prefix} - Peer Review",
                    "content": result,
                }
            ]
        if feature_id == "journal_recommend":
            return [
                {
                    "type": ArtifactType.SUMMARY.value,
                    "title": f"{title_prefix} - Journal Recommendations",
                    "content": result,
                }
            ]

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
        if feature_id == "experiment_design":
            return [
                {
                    "type": ArtifactType.METHODOLOGY.value,
                    "title": f"{title_prefix} - 实验设计",
                    "content": result,
                }
            ]

    if workspace_type == "software_copyright":
        if feature_id == "copyright_materials":
            return [
                {
                    "type": ArtifactType.COPYRIGHT_MATERIALS.value,
                    "title": (
                        f"{result.get('software_profile', {}).get('software_name', title_prefix)} "
                        "软著申请材料清单"
                    ),
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


async def persist_langgraph_artifacts(
    feature_id: str,
    workspace_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Persist artifacts for LangGraph feature results."""
    workspace_id = str(payload.get("workspace_id") or "")
    if not workspace_id:
        return []

    drafts = build_langgraph_artifact_drafts(
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
