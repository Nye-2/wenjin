"""Prism document domain service."""

from __future__ import annotations

import posixpath
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.prism.contracts import (
    PrismFileContentProjection,
    PrismFileContentUpdateCommand,
    PrismFileCreateCommand,
    PrismFileProjection,
    PrismFileRestoreCommand,
    PrismFileVersionCreateCommand,
    PrismFileVersionProjection,
    PrismFileWriteProjection,
    PrismPrimaryProjectCommand,
    PrismProjectProjection,
    PrismProtectedScopeProjection,
    PrismProtectedScopeUpsertCommand,
    PrismSurfaceProjection,
    PrismWorkspaceFileUpsertCommand,
)
from src.dataservice.domains.prism.projection import (
    document_to_projection,
    file_to_projection,
    project_to_projection,
    protected_scope_to_projection,
    version_to_projection,
)
from src.dataservice.domains.prism.repository import PrismRepository

_SUPPORTED_PRISM_EXTENSIONS = {
    ".md",
    ".markdown",
    ".tex",
    ".bib",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
}
_TEXT_MIME_BY_EXTENSION = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".tex": "text/x-tex",
    ".bib": "text/x-bibtex",
    ".svg": "image/svg+xml",
}
_IMAGE_MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def normalize_prism_file_path(path: str) -> str:
    """Normalize and validate a user-facing Prism path."""

    raw_path = str(path or "").strip().replace("\\", "/")
    if not raw_path:
        raise ValueError("Prism file path is required")
    if raw_path.startswith("/"):
        raise ValueError("Prism file path must be workspace-relative")
    normalized = posixpath.normpath(raw_path)
    if normalized in {"", "."} or normalized.startswith("../") or normalized == "..":
        raise ValueError("Prism file path cannot escape the workspace")
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Prism file path contains an unsafe segment")
    if any(part.startswith(".") for part in parts):
        raise ValueError("Prism file path cannot contain hidden path segments")
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in _SUPPORTED_PRISM_EXTENSIONS:
        raise ValueError(f"Unsupported Prism file extension: {suffix or '<none>'}")
    if normalized.startswith("memory/") or normalized == "memory":
        raise ValueError("Workspace memory is not stored in Prism")
    return normalized


def infer_prism_mime_type(path: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    suffix = PurePosixPath(path).suffix.lower()
    return _TEXT_MIME_BY_EXTENSION.get(suffix) or _IMAGE_MIME_BY_EXTENSION.get(suffix) or "application/octet-stream"


class PrismDataDomainService:
    """DataService-owned Prism document operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = PrismRepository(session)

    async def ensure_primary_project(self, command: PrismPrimaryProjectCommand) -> PrismSurfaceProjection:
        main_file = normalize_prism_file_path(command.main_file)
        command = command.model_copy(update={"main_file": main_file})
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
            await self.session.flush()
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
            await self.session.flush()
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
                await self.session.flush()
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
        command = command.model_copy(
            update={
                "path": normalize_prism_file_path(command.path),
                "mime_type": infer_prism_mime_type(command.path, command.mime_type),
            }
        )
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

    async def upsert_workspace_file(
        self,
        *,
        workspace_id: str,
        command: PrismWorkspaceFileUpsertCommand,
    ) -> PrismFileWriteProjection:
        path = normalize_prism_file_path(command.path)
        mime_type = infer_prism_mime_type(path, command.mime_type)
        surface = await self.get_surface(workspace_id)
        if surface is None:
            surface = await self.ensure_primary_project(
                PrismPrimaryProjectCommand(
                    workspace_id=workspace_id,
                    title="Workspace Files",
                    adapter_kind="workspace_files",
                    adapter_ref_id=None,
                    main_file="README.md",
                    adapter_metadata_json={"file_workspace": True},
                )
            )
        document = surface.documents[0] if surface.documents else None
        if document is None:
            raise RuntimeError("Prism workspace has no primary document")

        file_record = await self.repository.get_file_by_path(document.id, path)
        if file_record is None:
            file_record = self.repository.create_file(
                {
                    "workspace_id": workspace_id,
                    "document_id": document.id,
                    "path": path,
                    "file_role": command.file_role,
                    "mime_type": mime_type,
                    "sort_order": command.sort_order,
                    "metadata_json": dict(command.metadata_json or {}),
                }
            )
            await self.session.flush()
        else:
            file_record.file_role = command.file_role
            file_record.mime_type = mime_type
            file_record.sort_order = command.sort_order
            file_record.metadata_json = {
                **dict(file_record.metadata_json or {}),
                **dict(command.metadata_json or {}),
            }
            file_record.updated_at = datetime.now(UTC)

        version = None
        changed = False
        if command.content_hash:
            write = await self.append_file_content(
                workspace_id=workspace_id,
                file_id=str(file_record.id),
                command=PrismFileContentUpdateCommand(
                    content_inline=command.content_inline,
                    content_asset_id=command.content_asset_id,
                    content_hash=command.content_hash,
                    created_by=command.created_by,
                    mission_review_item_id=command.mission_review_item_id,
                    mission_commit_id=command.mission_commit_id,
                    metadata_json=dict(command.metadata_json or {}),
                ),
            )
            file_projection = write.file
            version = write.version
            changed = write.changed
        else:
            await self._finish()
            file_projection = file_to_projection(file_record)
        return PrismFileWriteProjection(file=file_projection, version=version, changed=changed)

    async def get_workspace_file_content(
        self,
        *,
        workspace_id: str,
        file_id: str,
    ) -> PrismFileContentProjection | None:
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
        )
        if file_record is None:
            return None
        version = await self.repository.get_current_file_version(file_record)
        return PrismFileContentProjection(
            file=file_to_projection(file_record),
            current_version=version_to_projection(version) if version else None,
        )

    async def append_file_content(
        self,
        *,
        workspace_id: str,
        file_id: str,
        command: PrismFileContentUpdateCommand,
    ) -> PrismFileWriteProjection:
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
        )
        if file_record is None:
            return PrismFileWriteProjection(
                file=PrismFileProjection(
                    id=file_id,
                    workspace_id=workspace_id,
                    document_id="",
                    path="",
                    file_role="missing",
                ),
                changed=False,
                skipped_reason="not_found",
            )
        if command.expected_current_hash and file_record.content_hash != command.expected_current_hash:
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                changed=False,
                skipped_reason="hash_mismatch",
            )
        if file_record.content_hash == command.content_hash:
            await self._finish()
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                version=(version_to_projection(await self.repository.get_current_file_version(file_record)) if file_record.current_version_id else None),
                changed=False,
                skipped_reason="unchanged",
            )
        version = await self.append_file_version(
            PrismFileVersionCreateCommand(
                file_id=file_id,
                mission_review_item_id=command.mission_review_item_id,
                mission_commit_id=command.mission_commit_id,
                content_inline=command.content_inline,
                content_asset_id=command.content_asset_id,
                content_hash=command.content_hash,
                created_by=command.created_by,
            )
        )
        return PrismFileWriteProjection(
            file=file_to_projection(file_record),
            version=version,
            changed=version is not None,
        )

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
                "mission_review_item_id": command.mission_review_item_id,
                "mission_commit_id": command.mission_commit_id,
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

    async def restore_file_version(
        self,
        *,
        workspace_id: str,
        file_id: str,
        command: PrismFileRestoreCommand,
    ) -> PrismFileWriteProjection:
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
        )
        if file_record is None:
            return PrismFileWriteProjection(
                file=PrismFileProjection(
                    id=file_id,
                    workspace_id=workspace_id,
                    document_id="",
                    path="",
                    file_role="missing",
                ),
                changed=False,
                skipped_reason="not_found",
            )
        if command.expected_current_hash and file_record.content_hash != command.expected_current_hash:
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                changed=False,
                skipped_reason="hash_mismatch",
            )
        version = await self.repository.get_file_version(command.version_id)
        if version is None or version.file_id != file_id:
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                changed=False,
                skipped_reason="version_not_found",
            )
        file_record.current_version_id = version.id
        file_record.content_hash = version.content_hash
        file_record.updated_at = datetime.now(UTC)
        await self._finish()
        return PrismFileWriteProjection(
            file=file_to_projection(file_record),
            version=version_to_projection(version),
            changed=True,
        )

    async def soft_delete_workspace_file(
        self,
        *,
        workspace_id: str,
        file_id: str,
        expected_current_hash: str | None = None,
    ) -> PrismFileWriteProjection:
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
        )
        if file_record is None:
            return PrismFileWriteProjection(
                file=PrismFileProjection(
                    id=file_id,
                    workspace_id=workspace_id,
                    document_id="",
                    path="",
                    file_role="missing",
                ),
                changed=False,
                skipped_reason="not_found",
            )
        if expected_current_hash and file_record.content_hash != expected_current_hash:
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                changed=False,
                skipped_reason="hash_mismatch",
            )
        self.repository.soft_delete_file(file_record)
        await self._finish()
        return PrismFileWriteProjection(
            file=file_to_projection(file_record),
            changed=True,
        )

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
