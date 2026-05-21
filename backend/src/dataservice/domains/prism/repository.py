"""Prism document repository."""

from __future__ import annotations

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
        result = await self.session.execute(
            select(PrismProjectRecord).where(PrismProjectRecord.id == project_id)
        )
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

    async def get_file(self, file_id: str) -> PrismFileRecord | None:
        result = await self.session.execute(
            select(PrismFileRecord).where(PrismFileRecord.id == file_id)
        )
        return result.scalar_one_or_none()

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
        result = await self.session.execute(
            select(PrismDocumentRecord)
            .where(PrismDocumentRecord.project_id == project_id)
            .order_by(PrismDocumentRecord.created_at.asc())
        )
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
        result = await self.session.execute(
            select(PrismProtectedScopeRecord)
            .where(PrismProtectedScopeRecord.project_id == project_id)
            .order_by(PrismProtectedScopeRecord.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def next_file_version_no(self, file_id: str) -> int:
        result = await self.session.execute(
            select(func.max(PrismFileVersionRecord.version_no)).where(
                PrismFileVersionRecord.file_id == file_id
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1
