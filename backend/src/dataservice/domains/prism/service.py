"""Prism document domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.prism.contracts import (
    PrismFileCreateCommand,
    PrismFileProjection,
    PrismFileVersionCreateCommand,
    PrismFileVersionProjection,
    PrismPrimaryProjectCommand,
    PrismProjectProjection,
    PrismProtectedScopeProjection,
    PrismProtectedScopeUpsertCommand,
    PrismSurfaceProjection,
)
from src.dataservice.domains.prism.projection import (
    document_to_projection,
    file_to_projection,
    project_to_projection,
    protected_scope_to_projection,
    version_to_projection,
)
from src.dataservice.domains.prism.repository import PrismRepository


class PrismDataDomainService:
    """DataService-owned Prism document operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = PrismRepository(session)

    async def ensure_primary_project(self, command: PrismPrimaryProjectCommand) -> PrismSurfaceProjection:
        project = await self.repository.get_primary_project(command.workspace_id)
        if project is None:
            project = self.repository.create_project(
                {
                    "workspace_id": command.workspace_id,
                    "role": "primary_manuscript",
                    "title": command.title,
                    "adapter_kind": command.adapter_kind,
                    "adapter_ref_id": command.adapter_ref_id,
                    "status": "active",
                    "settings_json": dict(command.settings_json or {}),
                    "adapter_metadata_json": {
                        **dict(command.adapter_metadata_json or {}),
                        "main_file": command.main_file,
                    },
                }
            )
            document = self.repository.create_document(
                {
                    "workspace_id": command.workspace_id,
                    "project_id": project.id,
                    "document_kind": "manuscript",
                    "title": command.title,
                    "adapter_kind": command.adapter_kind,
                    "status": "active",
                    "metadata_json": {"main_file": command.main_file},
                }
            )
            root_file = self.repository.create_file(
                {
                    "workspace_id": command.workspace_id,
                    "document_id": document.id,
                    "path": command.main_file,
                    "file_role": "main",
                    "mime_type": "text/x-tex" if command.adapter_kind == "latex" else "text/plain",
                    "sort_order": 0,
                    "metadata_json": {"adapter_kind": command.adapter_kind},
                }
            )
            document.root_file_id = root_file.id
        else:
            project.title = command.title
            project.adapter_kind = command.adapter_kind
            project.adapter_ref_id = command.adapter_ref_id
            project.settings_json = dict(command.settings_json or {})
            project.adapter_metadata_json = {
                **dict(project.adapter_metadata_json or {}),
                **dict(command.adapter_metadata_json or {}),
                "main_file": command.main_file,
            }
            project.updated_at = datetime.now(UTC)
            document = await self.repository.get_primary_document(project.id)
            if document is None:
                document = self.repository.create_document(
                    {
                        "workspace_id": command.workspace_id,
                        "project_id": project.id,
                        "document_kind": "manuscript",
                        "title": command.title,
                        "adapter_kind": command.adapter_kind,
                        "status": "active",
                        "metadata_json": {"main_file": command.main_file},
                    }
                )
            file_record = await self.repository.get_file_by_path(document.id, command.main_file)
            if file_record is None:
                file_record = self.repository.create_file(
                    {
                        "workspace_id": command.workspace_id,
                        "document_id": document.id,
                        "path": command.main_file,
                        "file_role": "main",
                        "mime_type": "text/x-tex" if command.adapter_kind == "latex" else "text/plain",
                        "sort_order": 0,
                        "metadata_json": {"adapter_kind": command.adapter_kind},
                    }
                )
            document.root_file_id = file_record.id
            document.title = command.title
            document.updated_at = datetime.now(UTC)
        await self._finish()
        surface = await self.get_surface(command.workspace_id)
        if surface is None:
            raise RuntimeError("Prism primary project was not persisted")
        return surface

    async def get_primary_project(self, workspace_id: str) -> PrismProjectProjection | None:
        project = await self.repository.get_primary_project(workspace_id)
        return project_to_projection(project) if project else None

    async def get_surface(self, workspace_id: str) -> PrismSurfaceProjection | None:
        project = await self.repository.get_primary_project(workspace_id)
        if project is None:
            return None
        documents = await self.repository.list_documents(project.id)
        files = []
        for document in documents:
            files.extend(await self.repository.list_files(document.id))
        return PrismSurfaceProjection(
            project=project_to_projection(project),
            documents=[document_to_projection(document) for document in documents],
            files=[file_to_projection(file_record) for file_record in files],
        )

    async def create_file(
        self,
        *,
        document_id: str,
        workspace_id: str,
        command: PrismFileCreateCommand,
    ) -> PrismFileProjection:
        existing = await self.repository.get_file_by_path(document_id, command.path)
        if existing is not None:
            return file_to_projection(existing)
        record = self.repository.create_file(
            {
                "workspace_id": workspace_id,
                "document_id": document_id,
                "path": command.path,
                "file_role": command.file_role,
                "mime_type": command.mime_type,
                "sort_order": command.sort_order,
                "metadata_json": dict(command.metadata_json or {}),
            }
        )
        await self._finish()
        return file_to_projection(record)

    async def append_file_version(
        self,
        command: PrismFileVersionCreateCommand,
    ) -> PrismFileVersionProjection | None:
        file_record = await self.repository.get_file(command.file_id)
        if file_record is None:
            return None
        version_no = await self.repository.next_file_version_no(command.file_id)
        version = self.repository.create_file_version(
            {
                "workspace_id": file_record.workspace_id,
                "file_id": command.file_id,
                "version_no": version_no,
                "review_item_id": command.review_item_id,
                "content_inline": command.content_inline,
                "content_asset_id": command.content_asset_id,
                "content_hash": command.content_hash,
                "created_by": command.created_by,
            }
        )
        file_record.current_version_id = version.id
        file_record.content_hash = command.content_hash
        file_record.updated_at = datetime.now(UTC)
        await self._finish()
        return version_to_projection(version)

    async def upsert_protected_scope(
        self,
        command: PrismProtectedScopeUpsertCommand,
    ) -> PrismProtectedScopeProjection:
        normalized_section_key = str(command.section_key or "")
        existing = await self.repository.get_protected_scope(
            project_id=command.project_id,
            file_path=command.file_path,
            section_key=normalized_section_key,
            scope=command.scope,
        )
        if existing is None:
            existing = self.repository.create_protected_scope(
                {
                    "workspace_id": command.workspace_id,
                    "project_id": command.project_id,
                    "document_id": command.document_id,
                    "file_id": command.file_id,
                    "file_path": command.file_path,
                    "section_key": normalized_section_key,
                    "scope": command.scope,
                    "reason": command.reason,
                    "source": command.source,
                    "metadata_json": dict(command.metadata_json or {}),
                }
            )
        else:
            existing.document_id = command.document_id
            existing.file_id = command.file_id
            existing.reason = command.reason
            existing.source = command.source
            existing.metadata_json = dict(command.metadata_json or {})
            existing.updated_at = datetime.now(UTC)
        await self._finish()
        return protected_scope_to_projection(existing)

    async def list_protected_scopes(
        self,
        project_id: str,
        *,
        limit: int = 200,
    ) -> list[PrismProtectedScopeProjection]:
        return [
            protected_scope_to_projection(record)
            for record in await self.repository.list_protected_scopes(
                project_id,
                limit=limit,
            )
        ]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
