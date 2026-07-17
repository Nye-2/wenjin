"""Prism document repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.prism.models import (
    PrismDocumentRecord,
    PrismFileRecord,
    PrismFileVersionRecord,
    PrismProjectRecord,
    PrismProtectedScopeRecord,
)


class PrismRepository:
    """Persistence operations for Prism aggregate records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_project(self, values: dict[str, Any]) -> PrismProjectRecord:
        record = PrismProjectRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_document(self, values: dict[str, Any]) -> PrismDocumentRecord:
        record = PrismDocumentRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_file(self, values: dict[str, Any]) -> PrismFileRecord:
        record = PrismFileRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_file_version(self, values: dict[str, Any]) -> PrismFileVersionRecord:
        record = PrismFileVersionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_protected_scope(self, values: dict[str, Any]) -> PrismProtectedScopeRecord:
        record = PrismProtectedScopeRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_project(self, project_id: str) -> PrismProjectRecord | None:
        result = await self.session.execute(select(PrismProjectRecord).where(PrismProjectRecord.id == project_id))
        return result.scalar_one_or_none()

    async def get_primary_project(
        self,
        workspace_id: str,
        *,
        role: str = "primary_manuscript",
    ) -> PrismProjectRecord | None:
        result = await self.session.execute(
            select(PrismProjectRecord)
            .where(
                PrismProjectRecord.workspace_id == workspace_id,
                PrismProjectRecord.role == role,
                PrismProjectRecord.status == "active",
                PrismProjectRecord.trashed_at.is_(None),
            )
            .order_by(PrismProjectRecord.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_project_by_adapter_ref(
        self,
        *,
        adapter_kind: str,
        adapter_ref_id: str,
    ) -> PrismProjectRecord | None:
        result = await self.session.execute(
            select(PrismProjectRecord)
            .where(
                PrismProjectRecord.adapter_kind == adapter_kind,
                PrismProjectRecord.adapter_ref_id == adapter_ref_id,
            )
            .order_by(PrismProjectRecord.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_primary_document(self, project_id: str) -> PrismDocumentRecord | None:
        result = await self.session.execute(
            select(PrismDocumentRecord)
            .where(
                PrismDocumentRecord.project_id == project_id,
                PrismDocumentRecord.document_kind == "manuscript",
                PrismDocumentRecord.status == "active",
            )
            .order_by(PrismDocumentRecord.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def lock_document(self, document_id: str) -> None:
        await self.session.execute(
            select(PrismDocumentRecord.id)
            .where(PrismDocumentRecord.id == document_id)
            .with_for_update()
        )

    async def get_file_by_path(self, document_id: str, path: str) -> PrismFileRecord | None:
        result = await self.session.execute(
            select(PrismFileRecord)
            .where(
                PrismFileRecord.document_id == document_id,
                PrismFileRecord.path == path,
                PrismFileRecord.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_file_by_workspace_path(self, workspace_id: str, path: str) -> PrismFileRecord | None:
        result = await self.session.execute(
            select(PrismFileRecord)
            .where(
                PrismFileRecord.workspace_id == workspace_id,
                PrismFileRecord.path == path,
                PrismFileRecord.deleted_at.is_(None),
            )
            .order_by(PrismFileRecord.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_file(self, file_id: str) -> PrismFileRecord | None:
        result = await self.session.execute(select(PrismFileRecord).where(PrismFileRecord.id == file_id))
        return result.scalar_one_or_none()

    async def get_file_for_workspace(
        self,
        *,
        workspace_id: str,
        file_id: str,
        project_id: str | None = None,
        for_update: bool = False,
    ) -> PrismFileRecord | None:
        statement = (
            select(PrismFileRecord)
            .join(
                PrismDocumentRecord,
                PrismDocumentRecord.id == PrismFileRecord.document_id,
            )
            .join(
                PrismProjectRecord,
                PrismProjectRecord.id == PrismDocumentRecord.project_id,
            )
            .where(
                PrismFileRecord.id == file_id,
                PrismFileRecord.workspace_id == workspace_id,
                PrismFileRecord.deleted_at.is_(None),
                PrismDocumentRecord.workspace_id == workspace_id,
                PrismDocumentRecord.status == "active",
                PrismProjectRecord.workspace_id == workspace_id,
                PrismProjectRecord.role == "primary_manuscript",
                PrismProjectRecord.status == "active",
                PrismProjectRecord.trashed_at.is_(None),
            )
        )
        if project_id is not None:
            statement = statement.where(PrismProjectRecord.id == project_id)
        if for_update:
            statement = statement.with_for_update(of=PrismFileRecord)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_file_version(self, version_id: str) -> PrismFileVersionRecord | None:
        result = await self.session.execute(select(PrismFileVersionRecord).where(PrismFileVersionRecord.id == version_id))
        return result.scalar_one_or_none()

    async def get_file_version_by_mission_commit(
        self,
        mission_commit_id: str,
    ) -> PrismFileVersionRecord | None:
        result = await self.session.execute(
            select(PrismFileVersionRecord).where(
                PrismFileVersionRecord.mission_commit_id == mission_commit_id
            )
        )
        return result.scalar_one_or_none()

    async def get_current_file_version(self, file_record: PrismFileRecord) -> PrismFileVersionRecord | None:
        if not file_record.current_version_id:
            return None
        return await self.get_file_version(str(file_record.current_version_id))

    async def get_previous_file_version(
        self,
        *,
        file_id: str,
        before_version_no: int,
    ) -> PrismFileVersionRecord | None:
        result = await self.session.execute(
            select(PrismFileVersionRecord)
            .where(
                PrismFileVersionRecord.file_id == file_id,
                PrismFileVersionRecord.version_no < before_version_no,
            )
            .order_by(PrismFileVersionRecord.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def soft_delete_file(self, file_record: PrismFileRecord) -> None:
        file_record.deleted_at = datetime.now(UTC)
        file_record.updated_at = datetime.now(UTC)

    async def get_protected_scope(
        self,
        *,
        project_id: str,
        file_path: str,
        section_key: str,
        scope: str,
    ) -> PrismProtectedScopeRecord | None:
        result = await self.session.execute(
            select(PrismProtectedScopeRecord).where(
                PrismProtectedScopeRecord.project_id == project_id,
                PrismProtectedScopeRecord.file_path == file_path,
                PrismProtectedScopeRecord.section_key == section_key,
                PrismProtectedScopeRecord.scope == scope,
            )
        )
        return result.scalar_one_or_none()

    async def list_documents(self, project_id: str) -> list[PrismDocumentRecord]:
        result = await self.session.execute(select(PrismDocumentRecord).where(PrismDocumentRecord.project_id == project_id).order_by(PrismDocumentRecord.created_at.asc()))
        return list(result.scalars().all())

    async def list_files(self, document_id: str) -> list[PrismFileRecord]:
        result = await self.session.execute(
            select(PrismFileRecord)
            .where(
                PrismFileRecord.document_id == document_id,
                PrismFileRecord.deleted_at.is_(None),
            )
            .order_by(PrismFileRecord.sort_order.asc(), PrismFileRecord.path.asc())
        )
        return list(result.scalars().all())

    async def list_protected_scopes(
        self,
        project_id: str,
        *,
        limit: int = 200,
    ) -> list[PrismProtectedScopeRecord]:
        result = await self.session.execute(select(PrismProtectedScopeRecord).where(PrismProtectedScopeRecord.project_id == project_id).order_by(PrismProtectedScopeRecord.updated_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def next_file_version_no(self, file_id: str) -> int:
        result = await self.session.execute(select(func.max(PrismFileVersionRecord.version_no)).where(PrismFileVersionRecord.file_id == file_id))
        current = result.scalar_one_or_none()
        return int(current or 0) + 1
