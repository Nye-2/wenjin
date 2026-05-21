"""Feature action resolution service.

Backend-side resolver for workspace feature action states.
Replaces frontend resolver logic to ensure SSOT consistency.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.database import Artifact, Workspace

# ---------------------------------------------------------------------------
# Feature → acceptable source artifact types
# ---------------------------------------------------------------------------

FEATURE_SOURCE_TYPES: dict[str, list[str]] = {
    "literature_management": [
        "deep_research_report",
        "literature_inventory",
        "literature_review",
        "literature_search_results",
    ],
    "paper_analysis": ["paper_analysis"],
    "writing": [
        "framework_outline",
        "paper_analysis",
        "literature_review",
        "paper_draft",
    ],
    "literature_review": [
        "literature_search_results",
        "paper_analysis",
        "framework_outline",
        "paper_draft",
    ],
    "framework_outline": [
        "literature_review",
        "paper_analysis",
        "paper_draft",
        "literature_search_results",
    ],
    "peer_review": [
        "paper_draft",
        "framework_outline",
        "paper_analysis",
        "thesis_chapter",
    ],
    "journal_recommend": [
        "framework_outline",
        "paper_draft",
        "paper_analysis",
        "literature_review",
    ],
    "experiment_design": [
        "proposal",
        "background_research",
        "methodology",
    ],
    "copyright_materials": ["copyright_materials"],
    "technical_description": [
        "technical_description",
        "copyright_materials",
    ],
    "patent_outline": ["patent_outline"],
    "prior_art_search": ["prior_art_report", "patent_outline"],
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _read_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _read_number_like(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            parsed = float(normalized)
            if not math.isfinite(parsed):
                return None
            if parsed == int(parsed):
                return int(parsed)
            return parsed
        except ValueError:
            return None
    return None


def _read_string_array_like(value: Any, max_items: int = 8) -> list[str]:
    if isinstance(value, list):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ][:max_items]
    if isinstance(value, str):
        return [
            item.strip()
            for item in re.split(r"[\n,，]+", value)
            if item.strip()
        ][:max_items]
    return []


def _read_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _workspace_fallback(workspace: Workspace | None) -> str:
    if workspace is None:
        return "未命名任务"
    return (
        _read_string(workspace.description)
        or _read_string(workspace.name)
        or "未命名任务"
    )


# ---------------------------------------------------------------------------
# Artifact content helpers
# ---------------------------------------------------------------------------

def _artifact_content(artifact: Artifact | None) -> dict[str, Any]:
    if artifact is None:
        return {}
    content = artifact.content
    if isinstance(content, dict):
        return content
    return {}


def _get_artifact_paper_title(artifact: Artifact | None) -> str | None:
    content = _artifact_content(artifact)
    return (
        _read_string(content.get("paper_title"))
        or _read_string(content.get("title"))
        or _read_string(artifact.title if artifact else None)
    )


def _get_artifact_topic(artifact: Artifact | None) -> str | None:
    content = _artifact_content(artifact)
    return (
        _read_string(content.get("topic"))
        or _read_string(content.get("keywords"))
        or _read_string(content.get("query"))
        or _get_artifact_paper_title(artifact)
        or _read_string(artifact.title if artifact else None)
    )


def _get_artifact_discipline(
    artifact: Artifact | None, workspace: Workspace | None
) -> str | None:
    content = _artifact_content(artifact)
    return _read_string(content.get("discipline")) or _read_string(
        workspace.discipline if workspace else None
    )


def _get_artifact_software_profile(
    artifact: Artifact | None,
) -> dict[str, Any] | None:
    content = _artifact_content(artifact)
    return _read_record(content.get("software_profile"))


def _format_sections_for_prompt(value: Any, max_items: int = 4) -> str | None:
    if not isinstance(value, list):
        return None
    parts = []
    for item in value[:max_items]:
        if not isinstance(item, dict):
            continue
        title = (
            _read_string(item.get("title"))
            or _read_string(item.get("name"))
            or _read_string(item.get("id"))
        )
        body = _read_string(item.get("content")) or _read_string(item.get("focus"))
        if not title and not body:
            continue
        parts.append(": ".join(filter(None, [title, body])))
    return "\n".join(parts) if parts else None


def _get_artifact_abstract(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    content = _artifact_content(artifact)
    artifact_type = artifact.type

    if artifact_type == "framework_outline":
        return _read_string(content.get("abstract"))
    if artifact_type == "paper_analysis":
        return _read_string(content.get("summary"))
    if artifact_type == "literature_review":
        return _read_string(content.get("summary"))
    if artifact_type == "deep_research_report":
        discovery = _read_record(content.get("discovery"))
        return _read_string(discovery.get("summary") if discovery else None) or _read_string(content.get("topic"))
    if artifact_type == "paper_draft":
        return _read_string(content.get("content"))

    return _read_string(content.get("abstract")) or _read_string(content.get("summary"))


def _get_artifact_excerpt(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    content = _artifact_content(artifact)
    artifact_type = artifact.type

    if artifact_type == "paper_draft":
        return _read_string(content.get("content"))
    if artifact_type == "thesis_chapter":
        return _read_string(content.get("markdown")) or _read_string(content.get("content"))
    if artifact_type == "framework_outline":
        abstract = _read_string(content.get("abstract"))
        sections = _format_sections_for_prompt(content.get("sections"))
        contributions = content.get("contributions")
        contrib_text = None
        if isinstance(contributions, list):
            contrib_text = "\n".join(
                item.strip()
                for item in contributions[:4]
                if isinstance(item, str) and item.strip()
            ) or None
        parts = [p for p in [abstract, sections, contrib_text] if p]
        return "\n\n".join(parts) if parts else None
    if artifact_type == "paper_analysis":
        summary = _read_string(content.get("summary"))
        sections = content.get("sections")
        if isinstance(sections, dict):
            normalized = []
            for item in list(sections.values())[:4]:
                if not isinstance(item, dict):
                    continue
                title = _read_string(item.get("title"))
                body = _read_string(item.get("content"))
                if not title and not body:
                    continue
                normalized.append(" ".join(filter(None, [title, body])))
            normalized_text = "\n".join(normalized) if normalized else None
            parts = [p for p in [summary, normalized_text] if p]
            return "\n\n".join(parts) if parts else None
        return summary
    if artifact_type == "deep_research_report":
        discovery = _read_record(content.get("discovery"))
        summary = _read_string(discovery.get("summary") if discovery else None)
        ideas = content.get("ideas")
        ideas_text = None
        if isinstance(ideas, list):
            ideas_text = "\n".join(
                (
                    str(_read_string(item.get("title")) or "")
                    or str(_read_string(item.get("description")) or "")
                )
                for item in ideas[:4]
                if isinstance(item, dict)
            ) or None
        gaps = content.get("gaps")
        gaps_text = None
        if isinstance(gaps, list):
            gaps_text = "\n".join(
                str(_read_string(item.get("description")) or "")
                for item in gaps[:3]
                if isinstance(item, dict)
            ) or None
        parts = [
            p
            for p in [
                _read_string(content.get("topic")),
                summary,
                f"研究创意\n{ideas_text}" if ideas_text else None,
                f"研究空白\n{gaps_text}" if gaps_text else None,
            ]
            if p
        ]
        return "\n\n".join(parts) if parts else None

    return (
        _read_string(content.get("content"))
        or _read_string(content.get("summary"))
        or _read_string(content.get("abstract"))
    )


def _get_artifact_objective(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    content = _artifact_content(artifact)
    artifact_type = artifact.type

    if artifact_type == "proposal":
        sections = content.get("sections")
        if isinstance(sections, list):
            for item in sections:
                if not isinstance(item, dict):
                    continue
                section_id = _read_string(item.get("id")) or ""
                title = _read_string(item.get("title")) or ""
                if section_id == "objectives" or "目标" in title:
                    return _read_string(item.get("content"))
    if artifact_type == "background_research":
        return _read_string(content.get("keywords")) or _read_string(content.get("summary"))
    if artifact_type == "methodology":
        return _read_string(content.get("objective")) or _read_string(content.get("topic"))

    return _read_string(content.get("objective"))


def _summarize_artifact_context(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    content = _artifact_content(artifact)
    sections = content.get("sections")
    section_names = None
    if isinstance(sections, list):
        section_names = "、".join(
            name
            for item in sections[:3]
            if isinstance(item, dict)
            and (name := _read_string(item.get("title")) or _read_string(item.get("name")))
        ) or None
    return (
        _read_string(content.get("summary"))
        or _read_string(content.get("abstract"))
        or _read_string(content.get("objective"))
        or _read_string(content.get("topic"))
        or section_names
        or _read_string(artifact.title)
    )


# ---------------------------------------------------------------------------
# Source artifact resolution
# ---------------------------------------------------------------------------

def _resolve_explicit_source_artifact_id(
    orchestration_params: dict[str, Any] | None,
) -> str | None:
    if orchestration_params is None:
        return None
    explicit = _read_string(orchestration_params.get("source_artifact_id"))
    if explicit:
        return explicit
    context_ids = orchestration_params.get("context_artifact_ids")
    if isinstance(context_ids, list):
        for item in context_ids:
            val = _read_string(item)
            if val:
                return val
    deep_ids = orchestration_params.get("deep_research_artifact_ids")
    if isinstance(deep_ids, list):
        for item in deep_ids:
            val = _read_string(item)
            if val:
                return val
    return None


def _resolve_feature_source_artifact(
    feature_id: str,
    artifacts: list[Artifact],
    explicit_artifact_id: str | None = None,
) -> Artifact | None:
    if explicit_artifact_id:
        for artifact in artifacts:
            if str(artifact.id) == explicit_artifact_id:
                return artifact
    accepted_types = FEATURE_SOURCE_TYPES.get(feature_id)
    if not accepted_types:
        return None
    sorted_artifacts = sorted(
        artifacts,
        key=lambda a: a.created_at,
        reverse=True,
    )
    for atype in accepted_types:
        for artifact in sorted_artifacts:
            if artifact.type == atype:
                return artifact
    return None


def _with_source_artifact(
    source_artifact: Artifact | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    if source_artifact is not None:
        params = dict(params)
        params["source_artifact_id"] = str(source_artifact.id)
    return params


# ---------------------------------------------------------------------------
# Feature action state builders
# ---------------------------------------------------------------------------

def _build_state(
    source_artifact: Artifact | None,
    follow_up_prompt: str,
    route_params: dict[str, Any],
    rerun_params: dict[str, Any] | None,
    rerun_unavailable_reason: str | None,
) -> dict[str, Any]:
    return {
        "source_artifact_id": str(source_artifact.id) if source_artifact else None,
        "follow_up_prompt": follow_up_prompt,
        "route_params": route_params,
        "rerun_params": rerun_params,
        "rerun_unavailable_reason": rerun_unavailable_reason,
    }


# ---------------------------------------------------------------------------
# Per-feature resolvers
# ---------------------------------------------------------------------------

def _resolve_deep_research(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _read_string(orchestration_params.get("query") if orchestration_params else None)
        or _workspace_fallback(workspace)
    )
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {"topic": topic},
        {"topic": topic, "query": topic} if topic else None,
        None if topic else "缺少可复用的研究主题。",
    )


def _resolve_literature_management(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    query = (
        _read_string(orchestration_params.get("query") if orchestration_params else None)
        or _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"query": query}),
        {"topic": query} if query else None,
        None if query else "缺少可复用的文献主题。",
    )


def _resolve_literature_search(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    query = (
        _read_string(orchestration_params.get("query") if orchestration_params else None)
        or _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _workspace_fallback(workspace)
    )
    discipline = (
        _read_string(orchestration_params.get("discipline") if orchestration_params else None)
        or _get_artifact_discipline(source_artifact, workspace)
    )
    rerun = {"query": query}
    if discipline:
        rerun["discipline"] = discipline
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {"query": query, "discipline": discipline},
        rerun if query else None,
        None if query else "缺少可复用的检索主题。",
    )


def _resolve_paper_analysis(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    reference_id = _read_string(
        orchestration_params.get("reference_id") if orchestration_params else None
    )
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _get_artifact_paper_title(source_artifact)
        or _workspace_fallback(workspace)
    )
    paper_abstract = (
        _read_string(orchestration_params.get("paper_abstract") if orchestration_params else None)
        or _get_artifact_abstract(source_artifact)
    )
    rerun: dict[str, Any] = {"paper_title": paper_title}
    if reference_id:
        rerun["reference_id"] = reference_id
    if paper_abstract:
        rerun["paper_abstract"] = paper_abstract
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(
            source_artifact,
            {
                "reference_id": reference_id,
                "paper_title": paper_title,
                "paper_abstract": paper_abstract,
            },
        ),
        rerun if reference_id or paper_title else None,
        None if reference_id or paper_title else "缺少可复用的参考文献标识或标题。",
    )


def _resolve_writing(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _get_artifact_paper_title(source_artifact)
        or _read_string(workspace.name if workspace else None)
        or "Untitled Paper"
    )
    section_type = (
        _read_string(orchestration_params.get("section_type") if orchestration_params else None)
        or _read_string(orchestration_params.get("section") if orchestration_params else None)
    )
    target_words = _read_number_like(
        orchestration_params.get("target_words") if orchestration_params else None
    )
    context_artifact_ids: list[str] = []
    if orchestration_params and isinstance(orchestration_params.get("context_artifact_ids"), list):
        context_artifact_ids = [
            item.strip()
            for item in orchestration_params["context_artifact_ids"]
            if isinstance(item, str) and item.strip()
        ]
    elif source_artifact is not None:
        context_artifact_ids = [str(source_artifact.id)]

    route: dict[str, Any] = {"paper_title": paper_title}
    if section_type:
        route["section_type"] = section_type
    if target_words is not None:
        route["target_words"] = target_words
    if context_artifact_ids:
        route["context_artifact_ids"] = context_artifact_ids
    route = _with_source_artifact(source_artifact, route)

    rerun = {k: v for k, v in route.items() if k != "source_artifact_id"}
    return _build_state(
        source_artifact,
        follow_up_prompt,
        route,
        rerun if paper_title else None,
        None if paper_title else "缺少可复用的论文标题。",
    )


def _resolve_literature_review(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    discipline = (
        _read_string(orchestration_params.get("discipline") if orchestration_params else None)
        or _get_artifact_discipline(source_artifact, workspace)
    )
    rerun: dict[str, Any] = {"topic": topic}
    if discipline:
        rerun["discipline"] = discipline
    if source_artifact is not None:
        rerun["context_artifact_ids"] = [str(source_artifact.id)]
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"topic": topic, "discipline": discipline}),
        rerun if topic else None,
        None if topic else "缺少可复用的综述主题。",
    )


def _resolve_framework_outline(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _get_artifact_paper_title(source_artifact)
        or _read_string(workspace.name if workspace else None)
        or "Untitled Paper"
    )
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    rerun: dict[str, Any] = {"paper_title": paper_title, "topic": topic}
    if source_artifact is not None:
        rerun["context_artifact_ids"] = [str(source_artifact.id)]
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"paper_title": paper_title, "topic": topic}),
        rerun if paper_title and topic else None,
        None if paper_title and topic else "缺少可复用的论文标题或研究主题。",
    )


def _resolve_peer_review(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _get_artifact_paper_title(source_artifact)
        or _read_string(workspace.name if workspace else None)
        or "Untitled Paper"
    )
    manuscript_excerpt = (
        _get_artifact_excerpt(source_artifact)
        or _read_string(
            orchestration_params.get("manuscript_excerpt") if orchestration_params else None
        )
    )
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"paper_title": paper_title}),
        {"paper_title": paper_title, "manuscript_excerpt": manuscript_excerpt}
        if manuscript_excerpt
        else None,
        None if manuscript_excerpt else "缺少可直接审阅的稿件内容。",
    )


def _resolve_journal_recommend(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _get_artifact_paper_title(source_artifact)
        or _read_string(workspace.name if workspace else None)
        or "Untitled Paper"
    )
    discipline = (
        _read_string(orchestration_params.get("discipline") if orchestration_params else None)
        or _get_artifact_discipline(source_artifact, workspace)
    )
    abstract = (
        _get_artifact_abstract(source_artifact)
        or _read_string(orchestration_params.get("abstract") if orchestration_params else None)
    )
    rerun: dict[str, Any] = {"paper_title": paper_title}
    if abstract:
        rerun["abstract"] = abstract
    if discipline:
        rerun["discipline"] = discipline
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"paper_title": paper_title, "discipline": discipline}),
        rerun if abstract else None,
        None if abstract else "缺少可用于投稿画像的摘要或研究简介。",
    )


def _resolve_opening_research(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    report_type = (
        _read_string(orchestration_params.get("report_type") if orchestration_params else None)
        or "opening_report"
    )
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {"topic": topic, "report_type": report_type},
        {"topic": topic, "report_type": report_type} if topic else None,
        None if topic else "缺少可复用的研究主题。",
    )


def _resolve_thesis_writing(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    action = (
        _read_string(orchestration_params.get("action") if orchestration_params else None)
        or "generate_outline"
    )
    paper_title = (
        _read_string(orchestration_params.get("paper_title") if orchestration_params else None)
        or _read_string(workspace.name if workspace else None)
        or "未命名论文"
    )
    target_words = _read_number_like(
        orchestration_params.get("target_words") if orchestration_params else None
    )
    chapter_title = _read_string(
        orchestration_params.get("chapter_title") if orchestration_params else None
    )
    chapter_index = _read_number_like(
        orchestration_params.get("chapter_index") if orchestration_params else None
    )
    deep_research_artifact_ids: list[str] = []
    if orchestration_params and isinstance(
        orchestration_params.get("deep_research_artifact_ids"), list
    ):
        deep_research_artifact_ids = [
            item.strip()
            for item in orchestration_params["deep_research_artifact_ids"]
            if isinstance(item, str) and item.strip()
        ]

    rerun: dict[str, Any] = {"action": action, "paper_title": paper_title}
    if target_words is not None:
        rerun["target_words"] = target_words
    if chapter_title:
        rerun["chapter_title"] = chapter_title
    if chapter_index is not None:
        rerun["chapter_index"] = chapter_index
    if deep_research_artifact_ids:
        rerun["deep_research_artifact_ids"] = deep_research_artifact_ids

    route: dict[str, Any] = {"action": action, "paper_title": paper_title}
    if target_words is not None:
        route["target_words"] = target_words
    if chapter_title:
        route["chapter_title"] = chapter_title
    if chapter_index is not None:
        route["chapter_index"] = chapter_index

    return _build_state(
        source_artifact,
        follow_up_prompt,
        route,
        rerun,
        None,
    )


def _resolve_figure_generation(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    description = (
        _read_string(orchestration_params.get("description") if orchestration_params else None)
        or _summarize_artifact_context(source_artifact)
    )
    figure_type = (
        _read_string(orchestration_params.get("type") if orchestration_params else None)
        or _read_string(orchestration_params.get("fig_type") if orchestration_params else None)
        or "flowchart"
    )
    chapter_index = _read_number_like(
        orchestration_params.get("chapter_index") if orchestration_params else None
    )
    rerun: dict[str, Any] = {"description": description, "type": figure_type}
    if chapter_index is not None:
        rerun["chapter_index"] = chapter_index
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {
            "description": description,
            "type": figure_type,
            "chapter_index": chapter_index,
        },
        rerun if description else None,
        None if description else "缺少可复用的图表描述。",
    )


def _resolve_experiment_design(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    objective = (
        _read_string(orchestration_params.get("objective") if orchestration_params else None)
        or _get_artifact_objective(source_artifact)
        or topic
    )
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(source_artifact, {"topic": topic, "objective": objective}),
        {"topic": topic, "objective": objective} if topic else None,
        None if topic else "缺少可复用的研究目标或任务主题。",
    )


def _resolve_proposal_outline(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    topic = (
        _read_string(orchestration_params.get("topic") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    proposal_type = _read_string(
        orchestration_params.get("proposal_type") if orchestration_params else None
    )
    period_months = _read_number_like(
        orchestration_params.get("period_months") if orchestration_params else None
    )
    rerun: dict[str, Any] = {"topic": topic}
    if proposal_type:
        rerun["proposal_type"] = proposal_type
    if period_months is not None:
        rerun["period_months"] = period_months
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {"topic": topic, "proposal_type": proposal_type, "period_months": period_months},
        rerun if topic else None,
        None if topic else "缺少可复用的课题主题。",
    )


def _resolve_background_research(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    keywords = (
        _read_string(orchestration_params.get("keywords") if orchestration_params else None)
        or _get_artifact_topic(source_artifact)
        or _workspace_fallback(workspace)
    )
    industry_scope = _read_string(
        orchestration_params.get("industry_scope") if orchestration_params else None
    )
    time_range = _read_string(
        orchestration_params.get("time_range") if orchestration_params else None
    )
    rerun: dict[str, Any] = {"keywords": keywords}
    if industry_scope:
        rerun["industry_scope"] = industry_scope
    if time_range:
        rerun["time_range"] = time_range
    return _build_state(
        source_artifact,
        follow_up_prompt,
        {"keywords": keywords, "industry_scope": industry_scope, "time_range": time_range},
        rerun if keywords else None,
        None if keywords else "缺少可复用的调研关键词。",
    )


def _resolve_patent_outline(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    content = _artifact_content(source_artifact)
    innovation_description = (
        _read_string(
            orchestration_params.get("innovation_description")
            if orchestration_params
            else None
        )
        or _read_string(content.get("innovation_description"))
        or _read_string(workspace.description if workspace else None)
        or _read_string(workspace.name if workspace else None)
        or _workspace_fallback(workspace)
    )
    technical_field = (
        _read_string(orchestration_params.get("technical_field") if orchestration_params else None)
        or _read_string(content.get("technical_field"))
        or _read_string(workspace.discipline if workspace else None)
    )
    application_scenario = _read_string(
        orchestration_params.get("application_scenario") if orchestration_params else None
    ) or _read_string(content.get("application_scenario"))
    implementation_method = _read_string(
        orchestration_params.get("implementation_method") if orchestration_params else None
    ) or _read_string(content.get("implementation_method"))
    rerun: dict[str, Any] = {"innovation_description": innovation_description}
    if technical_field:
        rerun["technical_field"] = technical_field
    if application_scenario:
        rerun["application_scenario"] = application_scenario
    if implementation_method:
        rerun["implementation_method"] = implementation_method
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(
            source_artifact,
            {
                "innovation_description": innovation_description,
                "technical_field": technical_field,
                "application_scenario": application_scenario,
                "implementation_method": implementation_method,
            },
        ),
        rerun if innovation_description else None,
        None if innovation_description else "缺少可复用的创新点描述。",
    )


def _resolve_prior_art_search(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    content = _artifact_content(source_artifact)
    orch_keywords = _read_string_array_like(
        orchestration_params.get("keywords") if orchestration_params else None
    )
    content_keywords = _read_string_array_like(content.get("keywords"))
    if orch_keywords:
        keywords = orch_keywords
    elif content_keywords:
        keywords = content_keywords
    else:
        keywords = [
            _read_string(content.get("innovation_description"))
            or _read_string(workspace.name if workspace else None)
            or _workspace_fallback(workspace),
            str(_read_string(content.get("technical_field")) or ""),
            str(_read_string(content.get("application_scenario")) or ""),
        ]
        keywords = [k for k in keywords if k]

    orch_ipc = _read_string_array_like(
        orchestration_params.get("ipc_codes") if orchestration_params else None
    )
    content_ipc = _read_string_array_like(content.get("ipc_codes"))
    ipc_codes = orch_ipc if orch_ipc else content_ipc

    time_range = (
        _read_string(orchestration_params.get("time_range") if orchestration_params else None)
        or _read_string(content.get("time_range"))
        or "近5年"
    )
    rerun: dict[str, Any] = {"keywords": keywords, "time_range": time_range}
    if ipc_codes:
        rerun["ipc_codes"] = ipc_codes
    return _build_state(
        source_artifact,
        follow_up_prompt,
        _with_source_artifact(
            source_artifact,
            {
                "keywords": keywords if keywords else None,
                "ipc_codes": ipc_codes if ipc_codes else None,
                "time_range": time_range,
            },
        ),
        rerun if keywords else None,
        None if keywords else "缺少可复用的检索关键词。",
    )


def _resolve_copyright_materials(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    software_profile = _get_artifact_software_profile(source_artifact)
    software_name = (
        _read_string(orchestration_params.get("software_name") if orchestration_params else None)
        or _read_string(software_profile.get("software_name") if software_profile else None)
        or _read_string(workspace.name if workspace else None)
        or "待确认软件"
    )
    version = (
        _read_string(orchestration_params.get("version") if orchestration_params else None)
        or _read_string(software_profile.get("version") if software_profile else None)
        or "V1.0"
    )
    applicant_name = (
        _read_string(orchestration_params.get("applicant_name") if orchestration_params else None)
        or _read_string(software_profile.get("applicant_name") if software_profile else None)
    )
    completion_date = (
        _read_string(
            orchestration_params.get("completion_date") if orchestration_params else None
        )
        or _read_string(software_profile.get("completion_date") if software_profile else None)
    )
    highlights = _read_string_array_like(
        orchestration_params.get("highlights") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("highlights") if software_profile else None
    )
    target_platforms = _read_string_array_like(
        orchestration_params.get("target_platforms") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("target_platforms") if software_profile else None
    )
    source_modules = _read_string_array_like(
        orchestration_params.get("source_modules") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("source_modules") if software_profile else None
    )

    route: dict[str, Any] = {"software_name": software_name, "version": version}
    if applicant_name:
        route["applicant_name"] = applicant_name
    if completion_date:
        route["completion_date"] = completion_date
    if highlights:
        route["highlights"] = highlights
    if target_platforms:
        route["target_platforms"] = target_platforms
    if source_modules:
        route["source_modules"] = source_modules
    route = _with_source_artifact(source_artifact, route)

    rerun = {k: v for k, v in route.items() if k != "source_artifact_id"}
    return _build_state(
        source_artifact,
        follow_up_prompt,
        route,
        rerun if software_name else None,
        None if software_name else "缺少可复用的软件基础信息。",
    )


def _resolve_technical_description(
    workspace: Workspace | None,
    orchestration_params: dict[str, Any] | None,
    source_artifact: Artifact | None,
    follow_up_prompt: str,
) -> dict[str, Any]:
    software_profile = _get_artifact_software_profile(source_artifact)
    software_name = (
        _read_string(orchestration_params.get("software_name") if orchestration_params else None)
        or _read_string(software_profile.get("software_name") if software_profile else None)
        or _read_string(workspace.name if workspace else None)
        or "待确认软件"
    )
    version = (
        _read_string(orchestration_params.get("version") if orchestration_params else None)
        or _read_string(software_profile.get("version") if software_profile else None)
        or "V1.0"
    )
    core_modules = _read_string_array_like(
        orchestration_params.get("core_modules") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("core_modules") if software_profile else None
    )
    deployment_architecture = (
        _read_string(
            orchestration_params.get("deployment_architecture")
            if orchestration_params
            else None
        )
        or _read_string(software_profile.get("deployment_architecture") if software_profile else None)
        or "B/S架构"
    )
    database_middleware = _read_string_array_like(
        orchestration_params.get("database_middleware") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("database_middleware") if software_profile else None
    )
    interface_protocols = _read_string_array_like(
        orchestration_params.get("interface_protocols") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("interface_protocols") if software_profile else None
    )
    highlights = _read_string_array_like(
        orchestration_params.get("highlights") if orchestration_params else None
    ) or _read_string_array_like(
        software_profile.get("highlights") if software_profile else None
    )

    route: dict[str, Any] = {
        "software_name": software_name,
        "version": version,
        "deployment_architecture": deployment_architecture,
    }
    if core_modules:
        route["core_modules"] = core_modules
    if database_middleware:
        route["database_middleware"] = database_middleware
    if interface_protocols:
        route["interface_protocols"] = interface_protocols
    if highlights:
        route["highlights"] = highlights
    route = _with_source_artifact(source_artifact, route)

    rerun = {k: v for k, v in route.items() if k != "source_artifact_id"}
    return _build_state(
        source_artifact,
        follow_up_prompt,
        route,
        rerun if software_name else None,
        None if software_name else "缺少可复用的软件技术信息。",
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_RESOLVERS: dict[str, Any] = {
    "deep_research": _resolve_deep_research,
    "literature_management": _resolve_literature_management,
    "literature_search": _resolve_literature_search,
    "paper_analysis": _resolve_paper_analysis,
    "writing": _resolve_writing,
    "literature_review": _resolve_literature_review,
    "framework_outline": _resolve_framework_outline,
    "peer_review": _resolve_peer_review,
    "journal_recommend": _resolve_journal_recommend,
    "opening_research": _resolve_opening_research,
    "thesis_writing": _resolve_thesis_writing,
    "figure_generation": _resolve_figure_generation,
    "experiment_design": _resolve_experiment_design,
    "proposal_outline": _resolve_proposal_outline,
    "background_research": _resolve_background_research,
    "patent_outline": _resolve_patent_outline,
    "prior_art_search": _resolve_prior_art_search,
    "copyright_materials": _resolve_copyright_materials,
    "technical_description": _resolve_technical_description,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_feature_action_state(
    feature_id: str,
    workspace: Workspace | None,
    artifacts: list[Artifact],
    orchestration_params: dict[str, Any] | None = None,
    explicit_source_artifact_id: str | None = None,
    follow_up_prompt: str = "",
) -> dict[str, Any]:
    """Resolve feature action state for a given feature.

    Args:
        feature_id: The feature identifier.
        workspace: The workspace record (for fallback names, discipline, etc).
        artifacts: List of artifacts in the workspace.
        orchestration_params: Optional params from the execution context.
        explicit_source_artifact_id: Optional explicit source artifact ID.
        follow_up_prompt: The follow-up prompt for the feature.

    Returns:
        A dict with source_artifact_id, follow_up_prompt, route_params,
        rerun_params, and rerun_unavailable_reason.
    """
    explicit = explicit_source_artifact_id or _resolve_explicit_source_artifact_id(
        orchestration_params
    )
    source_artifact = _resolve_feature_source_artifact(
        feature_id, artifacts, explicit
    )

    resolver = _RESOLVERS.get(feature_id)
    if resolver is None:
        return _build_state(
            source_artifact,
            follow_up_prompt,
            {},
            None,
            "当前卡片没有可复用的 artifact 执行上下文。",
        )

    return resolver(workspace, orchestration_params, source_artifact, follow_up_prompt)  # type: ignore[no-any-return]
