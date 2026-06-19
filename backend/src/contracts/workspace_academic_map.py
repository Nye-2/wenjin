"""Bounded academic workspace map contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MAX_TITLE = 160
_MAX_SUMMARY = 220


class AcademicMapSourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    title: str
    year: int | None = None
    tags: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)


class AcademicMapLibraryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_count: int = 0
    strong_sources: list[AcademicMapSourceV1] = Field(default_factory=list)
    citation_risks: list[str] = Field(default_factory=list)


class AcademicMapManuscriptSectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    path: str | None = None
    status: str | None = None
    word_estimate: int | None = None


class AcademicMapManuscriptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_project_id: str | None = None
    main_file: str | None = None
    sections: list[AcademicMapManuscriptSectionV1] = Field(default_factory=list)
    pending_prism_changes: int = 0


class AcademicMapDatasetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    summary: str | None = None
    content_hash: str | None = None


class AcademicMapScriptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    last_status: str | None = None


class AcademicMapArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: str | None = None
    source_script: str | None = None


class AcademicMapExperimentsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasets: list[AcademicMapDatasetV1] = Field(default_factory=list)
    scripts: list[AcademicMapScriptV1] = Field(default_factory=list)
    artifacts: list[AcademicMapArtifactV1] = Field(default_factory=list)


class AcademicMapDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    summary: str
    status: str | None = None


class AcademicMapMemoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    summary: str
    category: str | None = None


class AcademicMapTokenBudgetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_context_items: int = 24
    full_text_loaded: bool = False


class AcademicWorkspaceMapV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.academic_workspace_map.v1"] = "wenjin.academic_workspace_map.v1"
    workspace_id: str
    workspace_type: str
    generated_at: str
    topic_hints: list[str] = Field(default_factory=list)
    library: AcademicMapLibraryV1 = Field(default_factory=AcademicMapLibraryV1)
    manuscript: AcademicMapManuscriptV1 = Field(default_factory=AcademicMapManuscriptV1)
    experiments: AcademicMapExperimentsV1 = Field(default_factory=AcademicMapExperimentsV1)
    decisions: list[AcademicMapDecisionV1] = Field(default_factory=list)
    memory: list[AcademicMapMemoryV1] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    token_budget: AcademicMapTokenBudgetV1 = Field(default_factory=AcademicMapTokenBudgetV1)


def compact_workspace_map_summary(value: AcademicWorkspaceMapV1 | dict[str, Any] | None) -> dict[str, Any]:
    """Return a bounded summary safe for member context."""

    if value is None:
        return {}
    raw = value.model_dump(mode="json") if isinstance(value, AcademicWorkspaceMapV1) else value
    if not isinstance(raw, dict):
        return {}
    library = raw.get("library") if isinstance(raw.get("library"), dict) else {}
    manuscript = raw.get("manuscript") if isinstance(raw.get("manuscript"), dict) else {}
    experiments = raw.get("experiments") if isinstance(raw.get("experiments"), dict) else {}
    return {
        "schema_version": "wenjin.academic_workspace_map.summary.v1",
        "workspace_id": _optional_truncated(raw.get("workspace_id"), 80),
        "workspace_type": _optional_truncated(raw.get("workspace_type"), 40),
        "generated_at": _optional_truncated(raw.get("generated_at"), 80),
        "topic_hints": _bounded_strings(raw.get("topic_hints"), limit=10, max_chars=80),
        "library": {
            "source_count": int(library.get("source_count") or 0),
            "strong_sources": _compact_sources(library.get("strong_sources"), limit=12),
            "citation_risks": _bounded_strings(library.get("citation_risks"), limit=8, max_chars=160),
        },
        "manuscript": {
            "active_project_id": _optional_truncated(manuscript.get("active_project_id"), 120),
            "main_file": _optional_truncated(manuscript.get("main_file"), 160),
            "sections": _compact_sections(manuscript.get("sections"), limit=12),
            "pending_prism_changes": int(manuscript.get("pending_prism_changes") or 0),
        },
        "experiments": {
            "datasets": _compact_path_items(experiments.get("datasets"), limit=12, keep=("summary", "content_hash")),
            "scripts": _compact_path_items(experiments.get("scripts"), limit=12, keep=("last_status",)),
            "artifacts": _compact_path_items(experiments.get("artifacts"), limit=12, keep=("kind", "source_script")),
        },
        "decisions": _compact_summary_items(raw.get("decisions"), id_key="decision_id", limit=10),
        "memory": _compact_summary_items(raw.get("memory"), id_key="memory_id", limit=10),
        "open_questions": _bounded_strings(raw.get("open_questions"), limit=8, max_chars=160),
    }


def _compact_sources(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_key = _optional_truncated(item.get("source_key"), 160)
        title = _optional_truncated(item.get("title"), _MAX_TITLE)
        if not source_key or not title:
            continue
        result.append(
            {
                "source_key": source_key,
                "title": title,
                "year": item.get("year") if isinstance(item.get("year"), int) else None,
                "tags": _bounded_strings(item.get("tags"), limit=6, max_chars=60),
                "quality_flags": _bounded_strings(item.get("quality_flags"), limit=6, max_chars=80),
            }
        )
        if len(result) >= limit:
            break
    return result


def _compact_sections(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        section_id = _optional_truncated(item.get("section_id"), 120)
        if not section_id:
            continue
        result.append(
            {
                "section_id": section_id,
                "path": _optional_truncated(item.get("path"), 180),
                "status": _optional_truncated(item.get("status"), 80),
                "word_estimate": item.get("word_estimate") if isinstance(item.get("word_estimate"), int) else None,
            }
        )
        if len(result) >= limit:
            break
    return result


def _compact_path_items(value: Any, *, limit: int, keep: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _optional_truncated(item.get("path"), 240)
        if not path:
            continue
        compact = {"path": path}
        for key in keep:
            compact_value = _optional_truncated(item.get(key), _MAX_SUMMARY)
            if compact_value:
                compact[key] = compact_value
        result.append(compact)
        if len(result) >= limit:
            break
    return result


def _compact_summary_items(value: Any, *, id_key: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_id = _optional_truncated(item.get(id_key), 120)
        summary = _optional_truncated(item.get("summary"), _MAX_SUMMARY)
        if not item_id or not summary:
            continue
        compact = {id_key: item_id, "summary": summary}
        status = _optional_truncated(item.get("status"), 80)
        category = _optional_truncated(item.get("category"), 80)
        if status:
            compact["status"] = status
        if category:
            compact["category"] = category
        result.append(compact)
        if len(result) >= limit:
            break
    return result


def _bounded_strings(value: Any, *, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    for item in value:
        text = _optional_truncated(item, max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _optional_truncated(value: Any, max_chars: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."
