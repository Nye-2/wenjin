"""Build bounded academic workspace maps from existing workspace context."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.contracts.workspace_academic_map import AcademicWorkspaceMapV1, compact_workspace_map_summary


def build_academic_workspace_map_from_workspace_data(
    *,
    workspace_id: str,
    workspace_type: str,
    workspace_data: dict[str, Any] | None,
    generated_at: str | None = None,
) -> AcademicWorkspaceMapV1:
    """Create a deterministic academic workspace map from already-loaded context."""

    workspace_data = workspace_data if isinstance(workspace_data, dict) else {}
    generated_at = generated_at or datetime.now(UTC).isoformat()
    related_documents = workspace_data.get("related_documents")
    related_documents = related_documents if isinstance(related_documents, list) else []
    library_context = workspace_data.get("library_context")
    library_context = library_context if isinstance(library_context, dict) else {}
    manuscript_context = workspace_data.get("manuscript_context")
    manuscript_context = manuscript_context if isinstance(manuscript_context, dict) else {}
    sandbox_context = workspace_data.get("sandbox_context")
    sandbox_context = sandbox_context if isinstance(sandbox_context, dict) else {}
    workspace_file_summary = workspace_data.get("workspace_file_summary")
    workspace_file_summary = workspace_file_summary if isinstance(workspace_file_summary, dict) else {}
    workspace_history = workspace_data.get("workspace_history")
    workspace_history = workspace_history if isinstance(workspace_history, dict) else {}

    return AcademicWorkspaceMapV1(
        workspace_id=str(workspace_id or ""),
        workspace_type=str(workspace_type or "unknown"),
        generated_at=generated_at,
        topic_hints=_topic_hints(workspace_data, related_documents),
        library={
            "source_count": len(related_documents),
            "strong_sources": _strong_sources(related_documents),
            "citation_risks": _citation_risks(related_documents, library_context),
        },
        manuscript=_manuscript_summary(manuscript_context),
        experiments=_experiment_summary(sandbox_context, workspace_file_summary),
        decisions=_summary_records(workspace_history.get("decisions"), id_key="decision_id", limit=10),
        memory=_summary_records(workspace_history.get("memory"), id_key="memory_id", limit=10),
        open_questions=_open_questions(workspace_data),
        token_budget={"recommended_context_items": 24, "full_text_loaded": False},
    )


def build_compact_academic_workspace_map_summary(
    *,
    workspace_id: str,
    workspace_type: str,
    workspace_data: dict[str, Any] | None,
) -> dict[str, Any]:
    return compact_workspace_map_summary(
        build_academic_workspace_map_from_workspace_data(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            workspace_data=workspace_data,
        )
    )


def _topic_hints(workspace_data: dict[str, Any], related_documents: list[Any]) -> list[str]:
    hints: list[str] = []
    for key in ("topic", "research_topic", "capability_goal"):
        value = str(workspace_data.get(key) or "").strip()
        if value:
            hints.append(value)
    for item in related_documents[:10]:
        if not isinstance(item, dict):
            continue
        for tag in item.get("tags") or []:
            if str(tag).strip():
                hints.append(str(tag).strip())
        title = str(item.get("title") or "").strip()
        if title:
            hints.extend(_title_keywords(title))
    return _dedupe(hints, limit=12, max_chars=80)


def _strong_sources(related_documents: list[Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in related_documents:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("citation_key") or item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not source_key or not title:
            continue
        quality_flags: list[str] = []
        if item.get("doi"):
            quality_flags.append("has_doi")
        if item.get("citation_key"):
            quality_flags.append("has_citation_key")
        evidence_level = str(item.get("evidence_level") or "").strip()
        if evidence_level:
            quality_flags.append(f"evidence:{evidence_level}")
        sources.append(
            {
                "source_key": f"library:{source_key}",
                "title": title,
                "year": item.get("year") if isinstance(item.get("year"), int) else None,
                "tags": [],
                "quality_flags": quality_flags,
            }
        )
        if len(sources) >= 12:
            break
    return sources


def _citation_risks(related_documents: list[Any], library_context: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    missing_keys = [
        item for item in related_documents if isinstance(item, dict) and not str(item.get("citation_key") or "").strip()
    ]
    if missing_keys:
        risks.append(f"{len(missing_keys)} sources missing citation keys")
    citation_keys = library_context.get("citation_keys")
    if isinstance(citation_keys, list) and not citation_keys and related_documents:
        risks.append("library sources exist but no citable keys are available")
    return risks[:8]


def _manuscript_summary(manuscript_context: dict[str, Any]) -> dict[str, Any]:
    project = manuscript_context.get("project")
    project = project if isinstance(project, dict) else manuscript_context
    sections = manuscript_context.get("sections")
    sections = sections if isinstance(sections, list) else []
    return {
        "active_project_id": project.get("project_id") or project.get("id"),
        "main_file": project.get("main_file") or project.get("main_tex_path"),
        "sections": [
            {
                "section_id": str(item.get("section_id") or item.get("id") or item.get("title") or ""),
                "path": item.get("path") or item.get("relative_path"),
                "status": item.get("status") or item.get("state"),
                "word_estimate": item.get("word_estimate") if isinstance(item.get("word_estimate"), int) else None,
            }
            for item in sections[:12]
            if isinstance(item, dict)
        ],
        "pending_prism_changes": int(manuscript_context.get("pending_review_count") or 0),
    }


def _experiment_summary(sandbox_context: dict[str, Any], workspace_file_summary: dict[str, Any]) -> dict[str, Any]:
    dataset_provenance = workspace_file_summary.get("dataset_provenance")
    dataset_provenance = dataset_provenance if isinstance(dataset_provenance, list) else []
    artifacts = sandbox_context.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, list) else []
    scripts = sandbox_context.get("scripts")
    scripts = scripts if isinstance(scripts, list) else []
    return {
        "datasets": [
            {
                "path": item.get("path"),
                "summary": item.get("summary") or item.get("title"),
                "content_hash": item.get("content_hash"),
            }
            for item in dataset_provenance[:12]
            if isinstance(item, dict) and item.get("path")
        ],
        "scripts": [
            {
                "path": item.get("path"),
                "last_status": item.get("last_status") or item.get("status"),
            }
            for item in scripts[:12]
            if isinstance(item, dict) and item.get("path")
        ],
        "artifacts": [
            {
                "path": item.get("path"),
                "kind": item.get("kind"),
                "source_script": item.get("source_script"),
            }
            for item in artifacts[:12]
            if isinstance(item, dict) and item.get("path")
        ],
    }


def _summary_records(value: Any, *, id_key: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get(id_key) or item.get("id") or "").strip()
        summary = str(item.get("summary") or item.get("content") or item.get("title") or "").strip()
        if not item_id or not summary:
            continue
        result.append({id_key: item_id, "summary": summary, "status": item.get("status")})
        if len(result) >= limit:
            break
    return result


def _open_questions(workspace_data: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    for key in ("open_questions", "pending_questions"):
        value = workspace_data.get(key)
        if isinstance(value, list):
            questions.extend(str(item).strip() for item in value if str(item).strip())
    return _dedupe(questions, limit=8, max_chars=160)


def _title_keywords(title: str) -> list[str]:
    tokens = [
        token.strip(" ,.;:()[]{}").lower()
        for token in title.replace("/", " ").replace("-", " ").split()
    ]
    return [
        token
        for token in tokens
        if len(token) >= 5 and token not in {"using", "based", "study", "paper", "model", "models"}
    ][:4]


def _dedupe(items: list[str], *, limit: int, max_chars: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        text = text[:max_chars]
        key = text.lower()
        if key in seen:
            continue
        result.append(text)
        seen.add(key)
        if len(result) >= limit:
            break
    return result

