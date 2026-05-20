"""Canonical review/provenance service for workspace-owned Prism."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.database.models.prism import (
    PrismProtectedSection,
    PrismReviewItem,
    PrismSourceLink,
)

PENDING_STATUSES = ("pending", "deferred")
APPLIED_STATUSES = ("applied",)


def _project_workspace_id(project: LatexProject) -> str:
    workspace_id = str(getattr(project, "workspace_id", "") or "").strip()
    if not workspace_id:
        raise ValueError("Workspace-owned Prism project is missing workspace_id")
    return workspace_id


def _project_id(project: LatexProject) -> str:
    return str(project.id)


def _review_item_payload(item: PrismReviewItem) -> dict[str, Any]:
    preview_payload = _json_object(item.preview_payload)
    path = str(item.target_file_path or preview_payload.get("path") or "").strip()
    applied_at = getattr(item, "applied_at", None)
    payload = {
        "id": str(item.id),
        "logical_key": str(item.logical_key),
        "source_type": str(getattr(item, "source_type", "") or ""),
        "source_execution_id": getattr(item, "source_execution_id", None),
        "source_task_id": getattr(item, "source_task_id", None),
        "target_kind": str(getattr(item, "target_kind", "") or ""),
        "path": path,
        "title": str(getattr(item, "title", None) or path or item.logical_key),
        "reason": str(item.summary or preview_payload.get("reason") or ""),
        "status": str(item.status),
        "applied_at": applied_at.isoformat() if applied_at else None,
    }
    for key in (
        "pending_content",
        "pending_hash",
        "current_hash",
        "previous_content",
        "previous_hash",
        "applied_hash",
        "revert_signature",
        "source_execution_id",
        "source_task_id",
    ):
        if key in preview_payload:
            payload[key] = preview_payload[key]
    return payload


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _source_link_payload(item: PrismSourceLink) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "latex_project_id": str(item.latex_project_id),
        "review_item_id": item.review_item_id,
        "source_type": str(item.source_type),
        "source_id": str(item.source_id),
        "file_path": str(item.file_path),
        "section_key": str(item.section_key or ""),
        "quote": item.quote,
        "citation_key": item.citation_key,
        "usage": str(item.usage),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _protected_section_payload(item: PrismProtectedSection) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "latex_project_id": str(item.latex_project_id),
        "file_path": str(item.file_path),
        "section_key": str(item.section_key or ""),
        "scope": str(item.scope),
        "reason": item.reason,
        "source": str(item.source),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


class PrismReviewService:
    """Owns DB-backed Prism review state."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_project_review_items(
        self,
        project: LatexProject,
        *,
        statuses: tuple[str, ...] | None = None,
    ) -> list[PrismReviewItem]:
        stmt = select(PrismReviewItem).where(
            PrismReviewItem.workspace_id == _project_workspace_id(project),
            PrismReviewItem.latex_project_id == _project_id(project),
        )
        if statuses:
            stmt = stmt.where(PrismReviewItem.status.in_(statuses))
        stmt = stmt.order_by(PrismReviewItem.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_project_file_changes(
        self,
        project: LatexProject,
        *,
        statuses: tuple[str, ...] = PENDING_STATUSES,
    ) -> list[dict[str, Any]]:
        items = await self.list_project_review_items(project, statuses=statuses)
        return [_review_item_payload(item) for item in items]

    async def list_applied_file_changes(
        self,
        project: LatexProject,
    ) -> list[dict[str, Any]]:
        items = await self.list_project_review_items(project, statuses=APPLIED_STATUSES)
        return [_review_item_payload(item) for item in items if item.status != "reverted"]

    async def list_project_source_links(
        self,
        project: LatexProject,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(PrismSourceLink)
            .where(
                PrismSourceLink.workspace_id == _project_workspace_id(project),
                PrismSourceLink.latex_project_id == _project_id(project),
            )
            .order_by(PrismSourceLink.created_at.desc())
        )
        return [_source_link_payload(item) for item in result.scalars().all()]

    async def list_project_protected_sections(
        self,
        project: LatexProject,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(PrismProtectedSection)
            .where(
                PrismProtectedSection.workspace_id == _project_workspace_id(project),
                PrismProtectedSection.latex_project_id == _project_id(project),
            )
            .order_by(PrismProtectedSection.updated_at.desc())
        )
        return [_protected_section_payload(item) for item in result.scalars().all()]

    async def get_review_item(
        self,
        project: LatexProject,
        *,
        logical_key: str,
        statuses: tuple[str, ...] | None = None,
    ) -> PrismReviewItem | None:
        stmt = select(PrismReviewItem).where(
            PrismReviewItem.workspace_id == _project_workspace_id(project),
            PrismReviewItem.latex_project_id == _project_id(project),
            PrismReviewItem.logical_key == logical_key,
        )
        if statuses:
            stmt = stmt.where(PrismReviewItem.status.in_(statuses))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_pending_file_change(
        self,
        project: LatexProject,
        *,
        logical_key: str,
        path: str,
        reason: str,
        pending_content: str,
        pending_hash: str,
        current_hash: str | None,
        source_execution_id: str | None = None,
        source_task_id: str | None = None,
    ) -> PrismReviewItem:
        workspace_id = _project_workspace_id(project)
        now = datetime.now(tz=UTC)
        preview_payload: dict[str, Any] = {
            "mode": "diff",
            "logical_key": logical_key,
            "path": path,
            "reason": reason,
            "pending_content": pending_content,
            "pending_hash": pending_hash,
        }
        if current_hash is not None:
            preview_payload["current_hash"] = current_hash
        if source_execution_id:
            preview_payload["source_execution_id"] = source_execution_id
        if source_task_id:
            preview_payload["source_task_id"] = source_task_id

        item = await self.get_review_item(project, logical_key=logical_key)
        if item is None:
            item = PrismReviewItem(
                workspace_id=workspace_id,
                latex_project_id=_project_id(project),
                logical_key=logical_key,
                source_type="execution",
                source_execution_id=source_execution_id,
                source_task_id=source_task_id,
                target_kind="prism_file_change",
                target_file_path=path,
                target_room=None,
                target_item_id=None,
                title=path,
                summary=reason,
                status="pending",
                preview_payload=preview_payload,
                applied_at=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(item)
        else:
            item.source_type = "execution"
            item.source_execution_id = source_execution_id
            item.source_task_id = source_task_id
            item.target_kind = "prism_file_change"
            item.target_file_path = path
            item.title = path
            item.summary = reason
            item.status = "pending"
            item.preview_payload = preview_payload
            item.applied_at = None
            item.updated_at = now
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def clear_review_item(
        self,
        project: LatexProject,
        *,
        logical_key: str,
    ) -> None:
        item = await self.get_review_item(
            project,
            logical_key=logical_key,
            statuses=PENDING_STATUSES,
        )
        if item is None:
            return
        await self.db.delete(item)
        await self.db.commit()

    async def mark_applied(
        self,
        item: PrismReviewItem,
        *,
        previous_content: str,
        previous_hash: str,
        applied_hash: str,
        revert_signature: str,
    ) -> PrismReviewItem:
        payload = dict(item.preview_payload or {})
        payload.update(
            {
                "previous_content": previous_content,
                "previous_hash": previous_hash,
                "applied_hash": applied_hash,
                "revert_signature": revert_signature,
            }
        )
        item.status = "applied"
        item.preview_payload = payload
        item.applied_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def mark_rejected(
        self,
        item: PrismReviewItem,
        *,
        protect_section: bool,
        reason: str | None = None,
    ) -> PrismReviewItem:
        item.status = "rejected"
        item.summary = reason or item.summary
        if protect_section and item.target_file_path:
            await self.upsert_protected_section(
                workspace_id=item.workspace_id,
                latex_project_id=item.latex_project_id,
                file_path=item.target_file_path,
                section_key=item.logical_key,
                scope="section",
                reason=reason or item.summary,
                source="review_reject",
            )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def mark_reverted(self, item: PrismReviewItem) -> PrismReviewItem:
        item.status = "reverted"
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def upsert_protected_section(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        file_path: str,
        section_key: str | None,
        scope: str,
        reason: str | None,
        source: str,
    ) -> None:
        normalized_section_key = str(section_key or "")
        result = await self.db.execute(
            select(PrismProtectedSection).where(
                PrismProtectedSection.workspace_id == workspace_id,
                PrismProtectedSection.latex_project_id == latex_project_id,
                PrismProtectedSection.file_path == file_path,
                PrismProtectedSection.section_key == normalized_section_key,
                PrismProtectedSection.scope == scope,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            self.db.add(
                PrismProtectedSection(
                    workspace_id=workspace_id,
                    latex_project_id=latex_project_id,
                    file_path=file_path,
                    section_key=normalized_section_key,
                    scope=scope,
                    reason=reason,
                    source=source,
                )
            )
        else:
            item.reason = reason
            item.source = source
            item.updated_at = datetime.now(tz=UTC)

    async def record_source_link(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        review_item_id: str | None,
        source_type: str,
        source_id: str,
        file_path: str,
        section_key: str | None = None,
        quote: str | None = None,
        citation_key: str | None = None,
        usage: str = "background",
    ) -> PrismSourceLink:
        link = PrismSourceLink(
            workspace_id=workspace_id,
            latex_project_id=latex_project_id,
            review_item_id=review_item_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            section_key=str(section_key or ""),
            quote=quote,
            citation_key=citation_key,
            usage=usage,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link
