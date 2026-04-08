"""Artifact mapping and persistence helpers for workspace feature execution."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts.types import ArtifactType
from src.database import get_db_session

logger = logging.getLogger(__name__)

# Type for artifact builder functions
ArtifactBuilderFn = Callable[[str, str, str, dict], list]
_ARTIFACT_BUILDERS: dict[str, ArtifactBuilderFn] = {}


def _register(feature_id: str) -> Callable[[ArtifactBuilderFn], ArtifactBuilderFn]:
    """Decorator to register an artifact builder for a feature."""
    def decorator(fn: ArtifactBuilderFn) -> ArtifactBuilderFn:
        _ARTIFACT_BUILDERS[feature_id] = fn
        return fn
    return decorator


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")


# ---------------------------------------------------------------------------
# Thesis workspace builders
# ---------------------------------------------------------------------------

@_register("literature_management")
def _build_literature_management_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.LITERATURE_INVENTORY.value,
            "title": f"{title_prefix} - 文献管理盘点",
            "content": result,
        }
    ]


@_register("opening_research")
def _build_opening_research_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    report_type = str(result.get("report_type", "opening_report"))
    return [
        {
            "type": report_type,
            "title": f"{title_prefix} - {_report_type_label(report_type)}",
            "content": result,
        }
    ]


@_register("figure_generation")
def _build_figure_generation_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    description = str(result.get("description") or "图表")
    return [
        {
            "type": ArtifactType.FIGURE.value,
            "title": f"{title_prefix} - {description}",
            "content": result,
        }
    ]


@_register("compile_export")
def _build_compile_export_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = []
    latex_content = str(result.get("latex_content") or "").strip()
    bib_content = str(result.get("bib_content") or "").strip()
    if latex_content:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - 论文主稿 LaTeX",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": result.get("latex_project_id"),
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "pdf_endpoint": result.get("pdf_endpoint"),
                    "pdf_url": result.get("pdf_url"),
                    "paper_title": str(result.get("paper_title") or title_prefix),
                    "main_tex": latex_content,
                    "bib_tex": bib_content,
                    "compiler": result.get("compiler"),
                    "template": result.get("template"),
                    "source_summary": (
                        result.get("source_summary")
                        if isinstance(result.get("source_summary"), dict)
                        else {}
                    ),
                },
            }
        )

    drafts.append(
        {
            "type": ArtifactType.PAPER_DRAFT.value,
            "title": f"{title_prefix} - 编译预检结果",
            "content": result,
        }
    )
    return drafts


@_register("deep_research")
def _build_deep_research_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
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


@_register("thesis_writing")
def _build_thesis_writing_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
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


# ---------------------------------------------------------------------------
# SCI workspace builders
# ---------------------------------------------------------------------------

@_register("literature_search")
def _build_literature_search_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.LITERATURE_SEARCH_RESULTS.value,
            "title": f"{title_prefix} - Literature Search",
            "content": result,
        }
    ]


@_register("paper_analysis")
def _build_paper_analysis_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.PAPER_ANALYSIS.value,
            "title": f"{title_prefix} - Paper Analysis",
            "content": result,
        }
    ]


@_register("writing")
def _build_writing_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
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


@_register("literature_review")
def _build_literature_review_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.LITERATURE_REVIEW.value,
            "title": f"{title_prefix} - Literature Review",
            "content": result,
        }
    ]


@_register("framework_outline")
def _build_framework_outline_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = [
        {
            "type": ArtifactType.FRAMEWORK_OUTLINE.value,
            "title": f"{title_prefix} - Framework Outline",
            "content": result,
        }
    ]
    latex_project_id = str(result.get("latex_project_id") or "").strip()
    if latex_project_id:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - SCI LaTeX Project",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": latex_project_id,
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "paper_title": str(result.get("paper_title") or title_prefix),
                    "abstract": result.get("abstract"),
                    "keywords": result.get("keywords") if isinstance(result.get("keywords"), list) else [],
                    "section_map": result.get("section_map") if isinstance(result.get("section_map"), dict) else {},
                    "source_artifact_type": ArtifactType.FRAMEWORK_OUTLINE.value,
                },
            }
        )
    return drafts


@_register("peer_review")
def _build_peer_review_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.REVIEW.value,
            "title": f"{title_prefix} - Peer Review",
            "content": result,
        }
    ]


@_register("journal_recommend")
def _build_journal_recommend_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.SUMMARY.value,
            "title": f"{title_prefix} - Journal Recommendations",
            "content": result,
        }
    ]


# ---------------------------------------------------------------------------
# Patent workspace builders
# ---------------------------------------------------------------------------

@_register("patent_outline")
def _build_patent_outline_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = [
        {
            "type": ArtifactType.PATENT_OUTLINE.value,
            "title": f"{title_prefix} - 专利说明书框架",
            "content": result,
        }
    ]
    latex_project_id = str(result.get("latex_project_id") or "").strip()
    if latex_project_id:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - Patent LaTeX Project",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": latex_project_id,
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "section_map": result.get("section_map") if isinstance(result.get("section_map"), dict) else {},
                    "source_artifact_type": ArtifactType.PATENT_OUTLINE.value,
                },
            }
        )
    return drafts


@_register("prior_art_search")
def _build_prior_art_search_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.PRIOR_ART_REPORT.value,
            "title": f"{title_prefix} - 现有技术分析",
            "content": result,
        }
    ]


# ---------------------------------------------------------------------------
# Proposal workspace builders
# ---------------------------------------------------------------------------

@_register("proposal_outline")
def _build_proposal_outline_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = [
        {
            "type": ArtifactType.PROPOSAL.value,
            "title": f"{title_prefix} - 申报书大纲",
            "content": result,
        }
    ]
    latex_project_id = str(result.get("latex_project_id") or "").strip()
    if latex_project_id:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - Proposal LaTeX Project",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": latex_project_id,
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "project_title": str(result.get("topic") or title_prefix),
                    "section_map": result.get("section_map") if isinstance(result.get("section_map"), dict) else {},
                    "source_artifact_type": ArtifactType.PROPOSAL.value,
                },
            }
        )
    return drafts


@_register("background_research")
def _build_background_research_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.BACKGROUND_RESEARCH.value,
            "title": f"{title_prefix} - 背景调研报告",
            "content": result,
        }
    ]


@_register("experiment_design")
def _build_experiment_design_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    return [
        {
            "type": ArtifactType.METHODOLOGY.value,
            "title": f"{title_prefix} - 实验设计",
            "content": result,
        }
    ]


# ---------------------------------------------------------------------------
# Software copyright workspace builders
# ---------------------------------------------------------------------------

@_register("copyright_materials")
def _build_copyright_materials_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = [
        {
            "type": ArtifactType.COPYRIGHT_MATERIALS.value,
            "title": (
                f"{result.get('software_profile', {}).get('software_name', title_prefix)} "
                "软著申请材料清单"
            ),
            "content": result,
        }
    ]
    latex_project_id = str(result.get("latex_project_id") or "").strip()
    if latex_project_id:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - Copyright Materials LaTeX Project",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": latex_project_id,
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "section_file": result.get("section_file"),
                    "section_map": result.get("section_map") if isinstance(result.get("section_map"), dict) else {},
                    "source_artifact_type": ArtifactType.COPYRIGHT_MATERIALS.value,
                },
            }
        )
    return drafts


@_register("technical_description")
def _build_technical_description_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    title_prefix = workspace_name or "未命名工作区"
    drafts = [
        {
            "type": ArtifactType.TECHNICAL_DESCRIPTION.value,
            "title": f"{title_prefix} - 技术说明书",
            "content": result,
        }
    ]
    latex_project_id = str(result.get("latex_project_id") or "").strip()
    if latex_project_id:
        drafts.append(
            {
                "type": ArtifactType.LATEX_PROJECT.value,
                "title": f"{title_prefix} - Technical Description LaTeX Project",
                "content": {
                    "schema_version": "v2",
                    "latex_project_id": latex_project_id,
                    "main_file": str(result.get("main_file") or "main.tex"),
                    "section_map": result.get("section_map") if isinstance(result.get("section_map"), dict) else {},
                    "sync_conflicts": result.get("sync_conflicts") if isinstance(result.get("sync_conflicts"), list) else [],
                    "source_artifact_type": ArtifactType.TECHNICAL_DESCRIPTION.value,
                },
            }
        )
    return drafts


# ---------------------------------------------------------------------------
# Dispatch entry point
# ---------------------------------------------------------------------------

def build_langgraph_artifact_drafts(
    feature_id: str,
    workspace_name: str,
    workspace_type: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build artifact drafts by dispatching to the registered builder for feature_id."""
    builder = _ARTIFACT_BUILDERS.get(feature_id)
    if builder is None:
        logger.warning("No artifact builder registered for feature_id=%r", feature_id)
        return []
    return builder(feature_id, workspace_name, workspace_type, result)


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
