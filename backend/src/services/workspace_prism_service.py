"""Workspace-owned WenjinPrism lookup and projection service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.decision import Decision
from src.database.models.latex_project import LatexProject
from src.database.models.memory_fact import MemoryFact
from src.database.models.run_history import RunHistory
from src.services.prism_review_service import (
    APPLIED_STATUSES,
    PENDING_STATUSES,
    PrismReviewService,
)
from src.services.workspace_latex_projects import WorkspaceLatexProjectService

PRIMARY_MANUSCRIPT_ROLE = "primary_manuscript"


def _metadata_from_project(project: LatexProject) -> dict[str, Any]:
    llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _decision_payload(item: Decision) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "key": str(item.key),
        "value": str(item.value),
        "confidence": float(item.confidence or 0),
        "extracted_by": str(item.extracted_by),
        "created_at": _isoformat(item.created_at),
    }


def _memory_payload(item: MemoryFact) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "category": str(item.category),
        "content": str(item.content),
        "confidence": float(item.confidence or 0),
        "reference_count": int(item.reference_count or 0),
        "last_referenced_at": _isoformat(item.last_referenced_at),
        "created_at": _isoformat(item.created_at),
    }


def _run_history_payload(item: RunHistory) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "execution_id": str(item.execution_id),
        "capability_id": str(item.capability_id),
        "title": str(item.title),
        "summary": str(item.summary),
        "status": str(item.status),
        "artifact_count": int(item.artifact_count or 0),
        "duration_seconds": int(item.duration_seconds or 0),
        "created_at": _isoformat(item.created_at),
    }


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
        pending_items = await review_service.list_project_review_items(
            project,
            statuses=PENDING_STATUSES,
        )
        applied_items = await review_service.list_project_review_items(
            project,
            statuses=APPLIED_STATUSES,
        )
        file_changes = review_service.file_change_payloads(pending_items)
        applied_file_changes = review_service.file_change_payloads(
            [item for item in applied_items if item.status != "reverted"]
        )
        review_items = review_service.review_item_projections(
            [*pending_items, *applied_items]
        )
        source_links = await review_service.list_project_source_links(project)
        protected_sections = await review_service.list_project_protected_sections(project)
        decisions = await self._list_decisions(workspace_id)
        memory_preferences = await self._list_memory_preferences(workspace_id)
        recent_activity = await self._list_recent_activity(workspace_id)
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
            "review_items": review_items,
            "source_links": source_links,
            "protected_sections": protected_sections,
            "decisions": decisions,
            "memory_preferences": memory_preferences,
            "recent_activity": recent_activity,
            "review_summary": {
                "pending_count": len(file_changes),
                "applied_count": len(applied_file_changes),
                "source_link_count": len(source_links),
                "protected_section_count": len(protected_sections),
            },
            "context_summary": {
                "decision_count": len(decisions),
                "memory_preference_count": len(memory_preferences),
                "recent_activity_count": len(recent_activity),
            },
        }

    async def _list_decisions(self, workspace_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Decision)
            .where(
                Decision.workspace_id == workspace_id,
                Decision.deleted_at.is_(None),
                Decision.superseded_by.is_(None),
            )
            .order_by(Decision.created_at.desc())
            .limit(5)
        )
        return [_decision_payload(item) for item in result.scalars().all()]

    async def _list_memory_preferences(self, workspace_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(MemoryFact)
            .where(
                MemoryFact.workspace_id == workspace_id,
                MemoryFact.deleted_at.is_(None),
            )
            .order_by(
                MemoryFact.reference_count.desc(),
                MemoryFact.confidence.desc(),
                MemoryFact.created_at.desc(),
            )
            .limit(5)
        )
        return [_memory_payload(item) for item in result.scalars().all()]

    async def _list_recent_activity(self, workspace_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(RunHistory)
            .where(
                RunHistory.workspace_id == workspace_id,
                RunHistory.deleted_at.is_(None),
            )
            .order_by(RunHistory.created_at.desc())
            .limit(5)
        )
        return [_run_history_payload(item) for item in result.scalars().all()]

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
