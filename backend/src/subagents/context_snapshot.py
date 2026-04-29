"""Bounded context snapshot builder for subagent execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from src.agents.middlewares.discipline_context import DisciplineRegistry
from src.agents.thread_state import ThreadState
from src.subagents.task_builder import SubagentRuntimeContext
from src.workspace_features.skills import get_skill_by_id

logger = logging.getLogger(__name__)

_SECTION_LIMITS = {
    "workspace": 500,
    "skill": 1200,
    "template": 1200,
    "discipline": 600,
    "literature": 2200,
    "knowledge": 1600,
    "memory": 1200,
    "uploads": 800,
}
_TOTAL_LIMIT = 6500


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _truncate(text: str | None, *, limit: int) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    suffix = "\n...[truncated]"
    budget = max(0, limit - len(suffix))
    return normalized[:budget].rstrip() + suffix


def _state_value(state: Mapping[str, Any] | None, key: str) -> Any:
    if not isinstance(state, Mapping):
        return None
    return state.get(key)


def _render_template_snapshot(template_context: Mapping[str, Any] | None) -> str | None:
    if not isinstance(template_context, Mapping):
        return None

    lines: list[str] = []
    name = _normalize_optional_str(template_context.get("name"))
    if name:
        lines.append(f"- active_template: {name}")

    structure = template_context.get("structure")
    if isinstance(structure, Mapping):
        chapters = structure.get("chapters")
        if isinstance(chapters, list):
            titles = [
                _normalize_optional_str(chapter.get("title"))
                for chapter in chapters
                if isinstance(chapter, Mapping)
            ]
            normalized_titles = [title for title in titles if title]
            if normalized_titles:
                lines.append("- chapters: " + ", ".join(normalized_titles[:8]))

    format_spec = template_context.get("format_spec")
    if isinstance(format_spec, Mapping):
        bibliography_style = _normalize_optional_str(format_spec.get("bibliography_style"))
        if bibliography_style:
            lines.append(f"- bibliography_style: {bibliography_style}")

    content_guidelines = template_context.get("content_guidelines")
    if isinstance(content_guidelines, Mapping):
        abstract_limit = _normalize_optional_str(content_guidelines.get("abstract_word_limit"))
        keywords_count = _normalize_optional_str(content_guidelines.get("keywords_count"))
        if abstract_limit:
            lines.append(f"- abstract_word_limit: {abstract_limit}")
        if keywords_count:
            lines.append(f"- keywords_count: {keywords_count}")

    return "\n".join(lines) if lines else None


def _render_uploaded_files_snapshot(uploaded_files: Any) -> str | None:
    if not isinstance(uploaded_files, list):
        return None
    items: list[str] = []
    for item in uploaded_files[:8]:
        if not isinstance(item, Mapping):
            continue
        name = _normalize_optional_str(item.get("name"))
        path = _normalize_optional_str(item.get("path"))
        kind = _normalize_optional_str(item.get("kind")) or "transient"
        if not name or not path:
            continue
        items.append(f"- {name} [{kind}] {path}")
    return "\n".join(items) if items else None


def _render_artifact_snapshot(artifacts: list[Any]) -> str | None:
    if not artifacts:
        return None
    lines: list[str] = []
    grouped: dict[str, list[str]] = {}
    for artifact in artifacts:
        artifact_type = _normalize_optional_str(getattr(artifact, "type", None)) or "artifact"
        title = _normalize_optional_str(getattr(artifact, "title", None))
        if title is None:
            content = getattr(artifact, "content", None)
            if isinstance(content, Mapping):
                title = _normalize_optional_str(content.get("title"))
        if title is None:
            continue
        grouped.setdefault(artifact_type, []).append(title)

    for artifact_type, titles in grouped.items():
        preview = ", ".join(titles[:4])
        if preview:
            lines.append(f"- {artifact_type}: {preview}")
    return "\n".join(lines) if lines else None


async def _load_db_snapshot(
    runtime_context: SubagentRuntimeContext,
) -> dict[str, Any]:
    if runtime_context.workspace_id is None or runtime_context.user_id is None:
        return {}

    from src.academic.literature.index_service import IndexService
    from src.academic.services.artifact_service import ArtifactService
    from src.academic.services.workspace_service import WorkspaceService
    from src.database import Thread, get_db_session
    from src.services.template_service import TemplateService

    try:
        async with get_db_session() as db:
            workspace_service = WorkspaceService(db)
            workspace = await workspace_service.get(runtime_context.workspace_id)
            if workspace is None or str(workspace.user_id) != runtime_context.user_id:
                return {}

            snapshot: dict[str, Any] = {
                "workspace_type": _normalize_optional_str(getattr(workspace.type, "value", workspace.type)),
                "discipline": _normalize_optional_str(workspace.discipline),
                "workspace_description": _normalize_optional_str(workspace.description),
            }

            template = await TemplateService(db).get_active(str(workspace.id))
            if template is not None:
                snapshot["template_context"] = {
                    "name": template.name,
                    "structure": template.structure,
                    "format_spec": template.format_spec,
                    "content_guidelines": template.content_guidelines,
                }

            try:
                literature_context = await asyncio.wait_for(
                    IndexService(db).get_workspace_toc_summary(str(workspace.id)),
                    timeout=5.0,
                )
            except TimeoutError:
                literature_context = ""
            if literature_context:
                snapshot["literature_context"] = literature_context

            try:
                artifacts = await asyncio.wait_for(
                    ArtifactService(db).list_by_workspace(str(workspace.id), limit=12),
                    timeout=5.0,
                )
            except TimeoutError:
                artifacts = []
            if artifacts:
                snapshot["artifact_snapshot"] = _render_artifact_snapshot(artifacts)

            if runtime_context.thread_id is not None:
                thread = await db.get(Thread, runtime_context.thread_id)
                if (
                    thread is not None
                    and str(thread.user_id) == runtime_context.user_id
                    and _normalize_optional_str(thread.skill)
                ):
                    snapshot["current_skill"] = _normalize_optional_str(thread.skill)

            return snapshot
    except Exception:
        logger.debug(
            "Failed to build subagent DB snapshot for workspace %s",
            runtime_context.workspace_id,
            exc_info=True,
        )
        return {}


def _merge_snapshot_sources(
    state: Mapping[str, Any] | None,
    db_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    keys = (
        "workspace_type",
        "discipline",
        "workspace_description",
        "template_context",
        "literature_context",
        "knowledge_context",
        "artifact_snapshot",
        "memory_context",
        "discipline_norms",
        "current_skill",
        "uploaded_files",
    )
    for key in keys:
        state_value = _state_value(state, key)
        merged[key] = state_value if state_value not in (None, "", [], {}) else db_snapshot.get(key)
    return merged


def _needs_db_snapshot(state: Mapping[str, Any] | None) -> bool:
    if not isinstance(state, Mapping):
        return True

    has_workspace_identity = _state_value(state, "workspace_type") not in (None, "", [], {})
    has_context_payload = any(
        _state_value(state, key) not in (None, "", [], {})
        for key in (
            "discipline",
            "workspace_description",
            "template_context",
            "literature_context",
            "knowledge_context",
            "memory_context",
            "discipline_norms",
            "current_skill",
            "uploaded_files",
        )
    )
    return not (has_workspace_identity and has_context_payload)


def _render_snapshot_sections(snapshot: Mapping[str, Any]) -> list[str]:
    sections: list[str] = []

    workspace_lines: list[str] = []
    workspace_type = _normalize_optional_str(snapshot.get("workspace_type"))
    discipline = _normalize_optional_str(snapshot.get("discipline"))
    workspace_description = _truncate(
        _normalize_optional_str(snapshot.get("workspace_description")),
        limit=_SECTION_LIMITS["workspace"],
    )
    if workspace_type:
        workspace_lines.append(f"- workspace_type: {workspace_type}")
    if discipline:
        workspace_lines.append(f"- discipline: {discipline}")
    if workspace_description:
        workspace_lines.append(f"- workspace_description: {workspace_description}")
    if workspace_lines:
        sections.append("## Workspace Snapshot\n" + "\n".join(workspace_lines))

    current_skill = _normalize_optional_str(snapshot.get("current_skill"))
    if current_skill and workspace_type:
        skill_def = get_skill_by_id(workspace_type, current_skill)
        if skill_def is not None:
            skill_lines = [
                f"- current_skill: {skill_def.id}",
                f"- skill_name: {skill_def.name}",
            ]
            guidance = _truncate(skill_def.guidance_prompt, limit=_SECTION_LIMITS["skill"])
            if guidance:
                skill_lines.append("- guidance:")
                skill_lines.append(guidance)
            sections.append("## Preferred Skill\n" + "\n".join(skill_lines))

    template_snapshot = _truncate(
        _render_template_snapshot(snapshot.get("template_context")),
        limit=_SECTION_LIMITS["template"],
    )
    if template_snapshot:
        sections.append("## Template Constraints\n" + template_snapshot)

    discipline_norms = snapshot.get("discipline_norms")
    if isinstance(discipline_norms, Mapping) and discipline_norms:
        discipline_lines: list[str] = []
        citation_style = _normalize_optional_str(discipline_norms.get("citation_style"))
        writing_style = _normalize_optional_str(discipline_norms.get("writing_style"))
        structure = discipline_norms.get("structure")
        if citation_style:
            discipline_lines.append(f"- citation_style: {citation_style}")
        if writing_style:
            discipline_lines.append(f"- writing_style: {writing_style}")
        if isinstance(structure, list):
            normalized_structure = [
                _normalize_optional_str(item)
                for item in structure
            ]
            joined = " -> ".join(item for item in normalized_structure if item)
            if joined:
                discipline_lines.append(f"- expected_structure: {joined}")
        rendered = _truncate("\n".join(discipline_lines), limit=_SECTION_LIMITS["discipline"])
        if rendered:
            sections.append("## Discipline Norms\n" + rendered)
    elif discipline:
        registry = DisciplineRegistry()
        norms = registry.get_norms(discipline, workspace_type)
        if norms:
            normalized_norms = {
                "citation_style": norms.get("citation_style"),
                "writing_style": norms.get("writing_style"),
                "structure": norms.get("structure"),
            }
            fallback_sections = _render_snapshot_sections({"discipline_norms": normalized_norms})
            if fallback_sections:
                sections.extend(fallback_sections)

    literature_context = _truncate(
        _normalize_optional_str(snapshot.get("literature_context")),
        limit=_SECTION_LIMITS["literature"],
    )
    if literature_context:
        sections.append("## Literature Snapshot\n" + literature_context)

    knowledge_context = _truncate(
        _normalize_optional_str(snapshot.get("knowledge_context"))
        or _normalize_optional_str(snapshot.get("artifact_snapshot")),
        limit=_SECTION_LIMITS["knowledge"],
    )
    if knowledge_context:
        sections.append("## Artifact Snapshot\n" + knowledge_context)

    memory_context = _truncate(
        _normalize_optional_str(snapshot.get("memory_context")),
        limit=_SECTION_LIMITS["memory"],
    )
    if memory_context:
        sections.append("## Memory Snapshot\n" + memory_context)

    uploads_snapshot = _truncate(
        _render_uploaded_files_snapshot(snapshot.get("uploaded_files")),
        limit=_SECTION_LIMITS["uploads"],
    )
    if uploads_snapshot:
        sections.append("## Uploaded Files\n" + uploads_snapshot)

    return sections


def _render_snapshot_document(sections: list[str]) -> str | None:
    if not sections:
        return None
    body = "\n\n".join(sections)
    body = _truncate(body, limit=_TOTAL_LIMIT)
    if body is None:
        return None
    return (
        "## Inherited Workspace Context\n"
        "Use this snapshot as bounded parent context. Prefer it over generic assumptions.\n\n"
        f"{body}"
    )


async def build_subagent_context_snapshot(
    *,
    runtime_context: SubagentRuntimeContext,
    state: Mapping[str, Any] | ThreadState | None = None,
) -> str | None:
    """Build a bounded context snapshot for subagent execution."""
    db_snapshot = (
        await _load_db_snapshot(runtime_context)
        if _needs_db_snapshot(state)
        else {}
    )
    merged = _merge_snapshot_sources(state, db_snapshot)
    sections = _render_snapshot_sections(merged)
    return _render_snapshot_document(sections)
