"""LaTeX bridge orchestration helpers for workspace feature outputs.

Payload builders in ``workspace_features.services`` should remain pure content
assemblers. Graph orchestration can call these helpers to project a feature
result into a linked LaTeX workspace or to execute linked compile workflows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.database import get_db_session
from src.services.latex import LatexCompileService
from src.services.workspace_latex_projects import WorkspaceLatexProjectService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LatexSyncResult:
    """Structured LaTeX bridge result returned to feature graphs."""

    latex_project_id: str | None = None
    main_file: str | None = None
    section_file: str | None = None
    section_map: dict[str, str] = field(default_factory=dict)
    sync_conflicts: list[dict[str, Any]] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "latex_project_id": self.latex_project_id,
            "main_file": self.main_file,
            "section_map": dict(self.section_map),
            "sync_conflicts": [dict(conflict) for conflict in self.sync_conflicts],
        }
        if self.section_file is not None:
            payload["section_file"] = self.section_file
        return payload


@dataclass(slots=True)
class LatexCompileResult:
    """Structured linked compile result returned to thesis graphs."""

    latex_project_id: str | None = None
    main_file: str | None = None
    compile_status: str | None = None
    pdf_path: str | None = None
    pdf_url: str | None = None
    pdf_endpoint: str | None = None
    page_count: int | None = None
    compile_error: str | None = None
    compile_logs: str | None = None
    sync_conflicts: list[dict[str, Any]] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "latex_project_id": self.latex_project_id,
            "main_file": self.main_file,
            "compile_status": self.compile_status,
            "pdf_path": self.pdf_path,
            "pdf_url": self.pdf_url,
            "pdf_endpoint": self.pdf_endpoint,
            "page_count": self.page_count,
            "compile_error": self.compile_error,
            "compile_logs": self.compile_logs,
            "sync_conflicts": [dict(conflict) for conflict in self.sync_conflicts],
        }


def _truncate(value: str, max_len: int = 3000) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


def _normalize_sync_conflicts(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw_conflicts = metadata.get("sync_conflicts", []) if isinstance(metadata, dict) else []
    if not isinstance(raw_conflicts, list):
        return []
    return [dict(conflict) for conflict in raw_conflicts if isinstance(conflict, dict)]


def _normalize_title_candidate(value: Any) -> str:
    """Normalize a potential project title into a non-empty string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        normalized_items = [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
        return " / ".join(normalized_items)
    if value is None:
        return ""
    return str(value).strip()


def _pick_project_title(*candidates: Any, fallback: str) -> str:
    """Return the first non-empty normalized title candidate."""
    for candidate in candidates:
        normalized = _normalize_title_candidate(candidate)
        if normalized:
            return normalized
    return fallback


def _build_sync_result(
    linked_project: Any,
    *,
    section_map: dict[str, str] | None = None,
    section_file: str | None = None,
) -> LatexSyncResult:
    metadata = (
        linked_project.llm_config.get("metadata")
        if isinstance(getattr(linked_project, "llm_config", None), dict)
        else {}
    )
    return LatexSyncResult(
        latex_project_id=str(getattr(linked_project, "id", "") or "") or None,
        main_file=str(getattr(linked_project, "main_file", "") or "") or None,
        section_file=section_file,
        section_map=dict(section_map or {}),
        sync_conflicts=_normalize_sync_conflicts(metadata),
    )


async def sync_proposal_outline_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project proposal outline payload into the linked LaTeX workspace."""
    sections = payload.get("sections")
    project_title = _pick_project_title(payload.get("topic"), workspace_name, fallback="研究项目")
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_map = await bridge_service.sync_proposal_outline_project(
                workspace_id=workspace_id,
                project_title=project_title,
                sections=sections if isinstance(sections, list) else [],
            )
            return _build_sync_result(linked_project, section_map=section_map)
    except Exception:
        logger.exception("Failed to sync proposal outline into linked latex project")
        return LatexSyncResult()


async def sync_background_research_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project proposal background-research payload into the linked LaTeX workspace."""
    sections = payload.get("sections")
    project_title = _pick_project_title(payload.get("keywords"), workspace_name, fallback="背景调研")
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_map = await bridge_service.sync_proposal_sections(
                workspace_id=workspace_id,
                project_title=project_title,
                sections=sections if isinstance(sections, list) else [],
            )
            return _build_sync_result(linked_project, section_map=section_map)
    except Exception:
        logger.exception("Failed to sync background research into linked latex project")
        return LatexSyncResult()


async def sync_experiment_design_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project experiment-design payload into the linked LaTeX workspace."""
    project_title = _pick_project_title(payload.get("topic"), workspace_name, fallback="研究主题")
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_file, section_map = await bridge_service.sync_proposal_experiment_design(
                workspace_id=workspace_id,
                project_title=project_title,
                payload=payload,
            )
            return _build_sync_result(
                linked_project,
                section_map=section_map,
                section_file=section_file,
            )
    except Exception:
        logger.exception("Failed to sync experiment design into linked latex project")
        return LatexSyncResult()


async def sync_patent_outline_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project patent outline payload into the linked LaTeX workspace."""
    sections = payload.get("sections")
    claims_draft = payload.get("claims_draft")
    project_title = _pick_project_title(payload.get("innovation_description"), workspace_name, fallback="专利项目")
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_map = await bridge_service.sync_patent_outline_project(
                workspace_id=workspace_id,
                project_title=project_title,
                sections=sections if isinstance(sections, list) else [],
                claims_draft=claims_draft if isinstance(claims_draft, dict) else {},
            )
            return _build_sync_result(linked_project, section_map=section_map)
    except Exception:
        logger.exception("Failed to sync patent outline into linked latex project")
        return LatexSyncResult()


async def sync_sci_framework_outline_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project SCI framework-outline payload into the linked LaTeX workspace."""
    paper_title = _pick_project_title(payload.get("paper_title"), workspace_name, fallback="Untitled Paper")
    abstract = str(payload.get("abstract") or "").strip()
    keywords = payload.get("keywords")
    sections = payload.get("sections")
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_map = await bridge_service.sync_sci_outline_project(
                workspace_id=workspace_id,
                paper_title=paper_title or "Untitled Paper",
                abstract=abstract,
                keywords=keywords if isinstance(keywords, list) else [],
                sections=sections if isinstance(sections, list) else [],
            )
            return _build_sync_result(linked_project, section_map=section_map)
    except Exception:
        logger.exception("Failed to sync SCI framework outline into linked latex project")
        return LatexSyncResult()


async def sync_sci_writing_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project SCI section-draft payload into the linked LaTeX workspace."""
    paper_title = _pick_project_title(payload.get("paper_title"), workspace_name, fallback="Untitled Paper")
    section_type = str(payload.get("section_type") or "section").strip() or "section"
    section_title = str(payload.get("section_title") or "Section").strip() or "Section"
    content = str(payload.get("content") or "").strip()
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_file, section_map = await bridge_service.sync_sci_section_draft(
                workspace_id=workspace_id,
                paper_title=paper_title or "Untitled Paper",
                section_type=section_type,
                section_title=section_title,
                content=content,
            )
            return _build_sync_result(
                linked_project,
                section_map=section_map,
                section_file=section_file,
            )
    except Exception:
        logger.exception("Failed to sync SCI writing result into linked latex project")
        return LatexSyncResult()


async def sync_software_technical_description_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project software technical-description payload into the linked LaTeX workspace."""
    software_profile = payload.get("software_profile")
    sections = payload.get("sections")
    project_title = _pick_project_title(
        software_profile.get("software_name") if isinstance(software_profile, dict) else "",
        workspace_name,
        fallback="待确认软件",
    )
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_map = await bridge_service.sync_software_copyright_technical_description(
                workspace_id=workspace_id,
                project_title=project_title,
                sections=sections if isinstance(sections, dict) else {},
            )
            return _build_sync_result(linked_project, section_map=section_map)
    except Exception:
        logger.exception("Failed to sync technical description into linked latex project")
        return LatexSyncResult()


async def sync_software_materials_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    payload: dict[str, Any],
) -> LatexSyncResult:
    """Project copyright-materials payload into the linked LaTeX workspace."""
    software_profile = payload.get("software_profile")
    required_materials = payload.get("required_materials")
    review_checklist = payload.get("review_checklist")
    project_title = _pick_project_title(
        software_profile.get("software_name") if isinstance(software_profile, dict) else "",
        workspace_name,
        fallback="待确认软件",
    )
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            linked_project, section_file, section_map = await bridge_service.sync_software_copyright_materials(
                workspace_id=workspace_id,
                project_title=project_title,
                required_materials=required_materials if isinstance(required_materials, list) else [],
                review_checklist=review_checklist if isinstance(review_checklist, list) else [],
            )
            return _build_sync_result(
                linked_project,
                section_map=section_map,
                section_file=section_file,
            )
    except Exception:
        logger.exception("Failed to sync copyright materials into linked latex project")
        return LatexSyncResult()


async def compile_thesis_payload(
    *,
    workspace_id: str,
    payload: dict[str, Any],
) -> LatexCompileResult:
    """Sync and compile a thesis LaTeX payload in the linked project."""
    paper_title = _pick_project_title(payload.get("paper_title"), fallback="未命名论文")
    main_file = str(payload.get("main_file") or "main.tex").strip() or "main.tex"
    main_tex = str(payload.get("latex_content") or "")
    bib_tex = str(payload.get("bib_content") or "")
    template = str(payload.get("template") or "default").strip() or "default"
    normalized_compiler = str(payload.get("compiler") or "xelatex").lower().strip()
    if normalized_compiler not in {"xelatex", "pdflatex"}:
        normalized_compiler = "xelatex"

    source_summary = payload.get("source_summary")
    raw_template_assets = payload.get("template_assets")
    template_assets: list[dict[str, str]] = []
    if isinstance(raw_template_assets, list):
        for asset in raw_template_assets:
            if not isinstance(asset, dict):
                continue
            relative_path = str(asset.get("path") or "").strip()
            content = asset.get("content")
            if not relative_path or not isinstance(content, str):
                continue
            template_assets.append(
                {
                    "path": relative_path,
                    "content": content,
                }
            )
    try:
        async with get_db_session() as db:
            bridge_service = WorkspaceLatexProjectService(db)
            compile_service = LatexCompileService(db)
            linked_project = await bridge_service.sync_project(
                workspace_id=workspace_id,
                project_name=paper_title,
                main_file=main_file,
                main_tex=main_tex,
                bib_tex=bib_tex,
                extra_files=template_assets,
                template=template,
                metadata={
                    "source_summary": source_summary if isinstance(source_summary, dict) else {},
                    "bibliography_style": str(payload.get("bibliography_style") or "gbt7714"),
                    "output_language": str(payload.get("output_language") or ""),
                },
            )
            linked_metadata = (
                linked_project.llm_config.get("metadata")
                if isinstance(linked_project.llm_config, dict)
                else {}
            )
            compile_response = await compile_service.compile_project(
                linked_project,
                main_file=main_file,
                engine=normalized_compiler,
            )
    except Exception as exc:
        logger.exception("Failed to complete linked latex compile pipeline")
        raise RuntimeError(
            f"compile_export_failed: linked_latex_pipeline_failed: {exc}"
        ) from exc

    compile_logs = (
        str(compile_response.get("log"))
        if compile_response.get("log")
        else None
    )
    pdf_endpoint = (
        str(compile_response.get("pdf_endpoint"))
        if compile_response.get("pdf_endpoint")
        else None
    )
    pdf_path = (
        str(compile_response.get("pdf_path"))
        if compile_response.get("pdf_path")
        else None
    )
    page_count = (
        int(compile_response.get("page_count"))
        if compile_response.get("page_count") is not None
        else None
    )
    return LatexCompileResult(
        latex_project_id=str(getattr(linked_project, "id", "") or "") or None,
        main_file=main_file,
        compile_status="success" if bool(compile_response.get("ok")) else "failed",
        pdf_path=pdf_path,
        pdf_url=pdf_endpoint,
        pdf_endpoint=pdf_endpoint,
        page_count=page_count,
        compile_error=(
            str(compile_response.get("error"))
            if compile_response.get("error")
            else None
        ),
        compile_logs=_truncate(compile_logs or "", max_len=3000),
        sync_conflicts=_normalize_sync_conflicts(linked_metadata),
    )
