"""Prism document domain service."""

from __future__ import annotations

import hashlib
import posixpath
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.prism_visual_insertion import (
    canonical_visual_asset_path,
    canonical_workspace_asset_url,
    insert_after_prism_selection,
)
from src.dataservice.domains.asset.service import WorkspaceAssetService
from src.dataservice.domains.mission.write_authority import assert_active_mission_write
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
    PrismVisualInsertionCommand,
    PrismVisualInsertionProjection,
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
    ".pdf",
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
    ".pdf": "application/pdf",
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
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=workspace_id,
        )
        mission_commit_id = (
            command.mission_write_authority.mission_commit_id
            if command.mission_write_authority
            else None
        )
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

        if command.create_only:
            await self.repository.lock_document(document.id)
        file_record = await self.repository.get_file_by_path(document.id, path)
        if file_record is not None and command.create_only:
            applied_version = (
                await self.repository.get_file_version_by_mission_commit(
                    mission_commit_id
                )
                if mission_commit_id
                else None
            )
            if applied_version is not None:
                if (
                    applied_version.file_id != file_record.id
                    or applied_version.content_hash != command.content_hash
                ):
                    raise ValueError("Mission commit was reused with different Prism content")
                return PrismFileWriteProjection(
                    file=file_to_projection(file_record),
                    version=version_to_projection(applied_version),
                    changed=False,
                    skipped_reason="already_applied",
                )
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                changed=False,
                skipped_reason="already_exists",
            )
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
                    mission_write_authority=command.mission_write_authority,
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
        prism_project_id: str | None = None,
    ) -> PrismFileContentProjection | None:
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
            project_id=prism_project_id,
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
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=workspace_id,
        )
        mission_review_item_id = (
            command.mission_write_authority.mission_review_item_id
            if command.mission_write_authority
            else None
        )
        mission_commit_id = (
            command.mission_write_authority.mission_commit_id
            if command.mission_write_authority
            else None
        )
        file_record = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=file_id,
            for_update=True,
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
        applied_version = (
            await self.repository.get_file_version_by_mission_commit(
                mission_commit_id
            )
            if mission_commit_id
            else None
        )
        if applied_version is not None:
            if (
                applied_version.file_id != file_record.id
                or applied_version.content_hash != command.content_hash
            ):
                raise ValueError("Mission commit was reused with different Prism content")
            return PrismFileWriteProjection(
                file=file_to_projection(file_record),
                version=version_to_projection(applied_version),
                changed=False,
                skipped_reason="already_applied",
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
                mission_review_item_id=mission_review_item_id,
                mission_commit_id=mission_commit_id,
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

    async def insert_visual_asset(
        self,
        *,
        workspace_id: str,
        command: PrismVisualInsertionCommand,
    ) -> PrismVisualInsertionProjection:
        """Atomically bind a committed asset and append the manuscript version."""

        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=workspace_id,
            required=True,
        )
        mission_review_item_id = command.mission_write_authority.mission_review_item_id
        mission_commit_id = command.mission_write_authority.mission_commit_id

        target = await self.repository.get_file_for_workspace(
            workspace_id=workspace_id,
            file_id=command.target_file_id,
            project_id=command.prism_project_id,
            for_update=True,
        )
        if target is None:
            raise ValueError("Prism insertion target was not found")
        if PurePosixPath(target.path).suffix.lower() not in {".md", ".markdown", ".tex"}:
            raise ValueError("Academic visuals can only be inserted into Markdown or TeX files")

        applied_version = await self.repository.get_file_version_by_mission_commit(
            mission_commit_id
        )
        if applied_version is not None:
            if (
                applied_version.file_id != target.id
                or applied_version.content_hash != command.expected_content_hash
            ):
                raise ValueError("Mission commit was reused with different Prism content")
            asset = await WorkspaceAssetService(
                self.session,
                autocommit=False,
            ).get_asset(command.asset_id)
            if not _is_committed_visual_asset(
                asset,
                workspace_id=workspace_id,
                source_mission_commit_id=command.source_mission_commit_id,
            ):
                raise ValueError("Committed academic visual asset is unavailable")
            asset_path = canonical_visual_asset_path(
                content_hash=asset.content_hash,
                mime_type=asset.mime_type,
            )
            asset_file = await self.repository.get_file_by_path(target.document_id, asset_path)
            if asset_file is None:
                raise ValueError("Committed Prism insertion is missing its asset binding")
            return PrismVisualInsertionProjection(
                manuscript=PrismFileWriteProjection(
                    file=file_to_projection(target),
                    version=version_to_projection(applied_version),
                    changed=False,
                    skipped_reason="already_applied",
                ),
                asset_file=PrismFileWriteProjection(
                    file=file_to_projection(asset_file),
                    version=(
                        version_to_projection(await self.repository.get_current_file_version(asset_file))
                        if asset_file.current_version_id
                        else None
                    ),
                    changed=False,
                    skipped_reason="already_exists",
                ),
            )
        current_version = await self.repository.get_current_file_version(target)
        if current_version is None or current_version.content_inline is None:
            raise ValueError("Prism insertion target has no inline text revision")
        if (
            current_version.id != command.expected_current_version_id
            or target.content_hash != command.expected_current_hash
        ):
            raise ValueError("Prism insertion target changed before save")
        next_content = insert_after_prism_selection(
            content=current_version.content_inline,
            selection_byte_range=command.selection_byte_range,
            selection_hash=command.selection_hash,
            insertion=command.insertion,
        )
        content_hash = f"sha256:{hashlib.sha256(next_content.encode()).hexdigest()}"
        if content_hash != command.expected_content_hash:
            raise ValueError("Reviewed Prism insertion no longer matches its expected hash")

        asset = await WorkspaceAssetService(
            self.session,
            autocommit=False,
        ).get_asset(command.asset_id)
        if not _is_committed_visual_asset(
            asset,
            workspace_id=workspace_id,
            source_mission_commit_id=command.source_mission_commit_id,
        ):
            raise ValueError("Committed academic visual asset is unavailable")
        asset_path = canonical_visual_asset_path(
            content_hash=asset.content_hash,
            mime_type=asset.mime_type,
        )
        await self.repository.lock_document(target.document_id)
        asset_file = await self.repository.get_file_by_path(target.document_id, asset_path)
        asset_metadata = {
            "asset_id": asset.id,
            "asset_url": canonical_workspace_asset_url(
                workspace_id=workspace_id,
                storage_path=asset.storage_path,
            ),
            "source_mission_commit_id": command.source_mission_commit_id,
            "source": "committed_academic_visual",
        }
        asset_url = str(asset_metadata["asset_url"])
        if asset_path not in next_content and asset_url not in next_content:
            raise ValueError("Prism insertion does not reference its committed visual asset")
        asset_changed = False
        asset_version = None
        if asset_file is None:
            asset_file = self.repository.create_file(
                {
                    "workspace_id": workspace_id,
                    "document_id": target.document_id,
                    "path": asset_path,
                    "file_role": "academic_visual",
                    "mime_type": asset.mime_type,
                    "sort_order": 0,
                    "metadata_json": asset_metadata,
                }
            )
            await self.session.flush()
        else:
            existing_version = await self.repository.get_current_file_version(asset_file)
            if (
                existing_version is not None
                and (
                    existing_version.content_asset_id != asset.id
                    or existing_version.content_hash != asset.content_hash
                )
            ):
                raise ValueError("Prism visual path is bound to different content")
            asset_file.metadata_json = {
                **dict(asset_file.metadata_json or {}),
                **asset_metadata,
            }
            asset_file.updated_at = datetime.now(UTC)
        if asset_file.content_hash != asset.content_hash:
            asset_version = await self._append_file_version(
                PrismFileVersionCreateCommand(
                    file_id=str(asset_file.id),
                    content_asset_id=asset.id,
                    content_hash=asset.content_hash,
                    created_by=command.created_by,
                )
            )
            asset_changed = asset_version is not None
        elif asset_file.current_version_id:
            existing_version = await self.repository.get_current_file_version(asset_file)
            asset_version = version_to_projection(existing_version) if existing_version else None

        manuscript_version = await self._append_file_version(
            PrismFileVersionCreateCommand(
                file_id=str(target.id),
                mission_review_item_id=mission_review_item_id,
                mission_commit_id=mission_commit_id,
                content_inline=next_content,
                content_hash=content_hash,
                created_by=command.created_by,
            )
        )
        if manuscript_version is None:
            raise RuntimeError("Prism insertion did not produce a manuscript version")
        target.metadata_json = {
            **dict(target.metadata_json or {}),
            **dict(command.metadata_json or {}),
            "last_visual_asset_id": asset.id,
            "last_visual_mission_commit_id": mission_commit_id,
        }
        await self._finish()
        return PrismVisualInsertionProjection(
            manuscript=PrismFileWriteProjection(
                file=file_to_projection(target),
                version=manuscript_version,
                changed=True,
            ),
            asset_file=PrismFileWriteProjection(
                file=file_to_projection(asset_file),
                version=asset_version,
                changed=asset_changed,
                skipped_reason=None if asset_changed else "already_exists",
            ),
        )

    async def append_file_version(
        self,
        command: PrismFileVersionCreateCommand,
    ) -> PrismFileVersionProjection | None:
        version = await self._append_file_version(command)
        if version is not None:
            await self._finish()
        return version

    async def _append_file_version(
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


def _is_committed_visual_asset(
    asset: object | None,
    *,
    workspace_id: str,
    source_mission_commit_id: str,
) -> bool:
    if asset is None:
        return False
    metadata = dict(getattr(asset, "metadata_json", {}) or {})
    return bool(
        getattr(asset, "workspace_id", None) == workspace_id
        and getattr(asset, "deleted_at", None) is None
        and getattr(asset, "source_kind", None) == "mission_review_item"
        and getattr(asset, "content_hash", None)
        and getattr(asset, "mime_type", None)
        and metadata.get("mission_commit_id") == source_mission_commit_id
    )
