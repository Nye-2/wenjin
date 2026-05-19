"""Workspace-owned WenjinPrism lookup and projection service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.services.workspace_latex_projects import WorkspaceLatexProjectService

PRIMARY_MANUSCRIPT_ROLE = "primary_manuscript"


def _metadata_from_project(project: LatexProject) -> dict[str, Any]:
    llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _normalize_file_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


class WorkspacePrismService:
    """Resolve the canonical Prism manuscript bound to a workspace."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.bridge = WorkspaceLatexProjectService(db)

    async def get_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> LatexProject | None:
        explicit_result = await self.db.execute(
            select(LatexProject)
            .where(
                LatexProject.user_id == user_id,
                LatexProject.workspace_id == workspace_id,
                LatexProject.surface_role == PRIMARY_MANUSCRIPT_ROLE,
            )
            .order_by(LatexProject.updated_at.desc())
            .limit(1)
        )
        explicit = explicit_result.scalar_one_or_none()
        if explicit is not None:
            return explicit

        legacy_result = await self.db.execute(
            select(LatexProject)
            .where(
                LatexProject.user_id == user_id,
                LatexProject.workspace_id.is_(None),
                LatexProject.llm_config.is_not(None),
            )
            .where(
                and_(
                    LatexProject.llm_config["workspace_id"].as_string() == workspace_id,
                    LatexProject.llm_config["bridge"].as_string()
                    == "workspace_latex_project",
                )
            )
            .order_by(LatexProject.updated_at.desc())
            .limit(1)
        )
        return legacy_result.scalar_one_or_none()

    async def ensure_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
        project_name: str,
    ) -> LatexProject:
        project = await self.get_primary_project(workspace_id, user_id=user_id)
        if project is None:
            project = await self.bridge.ensure_workspace_project(
                workspace_id=workspace_id,
                project_name=project_name,
            )
        project.workspace_id = workspace_id
        project.surface_role = PRIMARY_MANUSCRIPT_ROLE
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def get_surface_projection(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        project = await self.get_primary_project(workspace_id, user_id=user_id)
        if project is None:
            raise ValueError(f"Workspace Prism not found: {workspace_id}")

        metadata = _metadata_from_project(project)
        file_changes = _normalize_file_changes(metadata.get("file_changes"))
        applied_file_changes = _normalize_file_changes(
            metadata.get("applied_file_changes")
        )
        main_file = str(project.main_file or "main.tex")
        target_files: list[str] = [main_file]
        raw_section_map = metadata.get("section_map")
        section_paths = (
            raw_section_map.values() if isinstance(raw_section_map, dict) else []
        )
        for value in section_paths:
            text = str(value).strip() if value is not None else ""
            if text and text not in target_files:
                target_files.append(text)
        for change in [*file_changes, *applied_file_changes]:
            text = str(change.get("path") or "").strip()
            if text and text not in target_files:
                target_files.append(text)

        return {
            "workspace_id": workspace_id,
            "latex_project_id": str(project.id),
            "surface_role": getattr(project, "surface_role", None)
            or PRIMARY_MANUSCRIPT_ROLE,
            "url": f"/workspaces/{workspace_id}/prism",
            "main_file": main_file,
            "compile_status": None,
            "has_pending_changes": bool(file_changes),
            "target_files": target_files,
            "file_changes": file_changes,
            "applied_file_changes": applied_file_changes,
        }

    async def resolve_workspace_from_project(
        self,
        project_id: str,
        *,
        user_id: str,
    ) -> tuple[str | None, LatexProject | None]:
        project = await self.db.get(LatexProject, project_id)
        if project is None or str(project.user_id) != str(user_id):
            return None, None

        if (
            project.workspace_id
            and (project.surface_role or PRIMARY_MANUSCRIPT_ROLE)
            == PRIMARY_MANUSCRIPT_ROLE
        ):
            return str(project.workspace_id), project

        llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
        if llm_config.get("bridge") == "workspace_latex_project":
            workspace_id = str(llm_config.get("workspace_id") or "").strip()
            if workspace_id:
                return workspace_id, project
        return None, project
