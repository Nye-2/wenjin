"""Workspace-owned WenjinPrism lookup and projection service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.services.prism_review_service import PrismReviewService
from src.services.workspace_latex_projects import WorkspaceLatexProjectService

PRIMARY_MANUSCRIPT_ROLE = "primary_manuscript"


def _metadata_from_project(project: LatexProject) -> dict[str, Any]:
    llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


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

        return None

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
        review_service = PrismReviewService(self.db)
        file_changes = await review_service.list_project_file_changes(project)
        applied_file_changes = await review_service.list_applied_file_changes(project)
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

    async def get_binding_integrity_report(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Report workspaces with missing or duplicate primary Prism projects."""

        params: dict[str, Any] = {"surface_role": PRIMARY_MANUSCRIPT_ROLE}
        user_filter = ""
        if user_id is not None:
            params["user_id"] = user_id
            user_filter = "where w.user_id = :user_id"

        result = await self.db.execute(
            text(
                f"""
                select
                    w.id as workspace_id,
                    w.user_id as user_id,
                    w.name as workspace_name,
                    count(lp.id) as primary_count
                from workspaces w
                left join latex_projects lp
                  on lp.workspace_id = w.id
                 and lp.surface_role = :surface_role
                {user_filter}
                group by w.id, w.user_id, w.name
                having count(lp.id) = 0 or count(lp.id) > 1
                order by w.id
                """
            ),
            params,
        )
        missing_primary: list[dict[str, Any]] = []
        duplicate_primary: list[dict[str, Any]] = []
        for row in result.mappings():
            item = {
                "workspace_id": str(row["workspace_id"]),
                "user_id": str(row["user_id"]),
                "workspace_name": str(row["workspace_name"] or ""),
                "primary_count": int(row["primary_count"] or 0),
            }
            if item["primary_count"] == 0:
                missing_primary.append(item)
            else:
                duplicate_primary.append(item)

        return {
            "missing_primary": missing_primary,
            "duplicate_primary": duplicate_primary,
        }
