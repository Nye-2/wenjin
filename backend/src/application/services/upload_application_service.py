"""Application orchestration for thread uploads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.routers.thread_contracts import ThreadAttachment, ThreadUploadKind
from src.services import ThreadService
from src.services.layout_preprocess_orchestrator import LayoutPreprocessOrchestrator
from src.services.references import SourceLibraryImportService
from src.services.thread_upload_service import ThreadUploadService
from src.services.upload_preflight_policy import UploadPreflightPolicy
from src.services.upload_preprocessor import UploadPreprocessor
from src.services.workspace_upload_service import WorkspaceUploadService
from src.workspace_events import publish_workspace_event


class ThreadUploadResponse(BaseModel):
    """Response for thread-scoped uploads."""

    success: bool
    files: list[ThreadAttachment]
    message: str


class UploadApplicationService:
    """Coordinate thread, literature, and workspace-context upload use cases."""

    def __init__(
        self,
        *,
        thread_service: ThreadService,
        workspace_service: Any,
        artifact_service: Any,
        task_service: Any,
        upload_preprocessor: UploadPreprocessor,
        dataservice: AsyncDataServiceClient,
        preflight_policy: UploadPreflightPolicy | None = None,
        thread_uploads: ThreadUploadService | None = None,
        preprocess_orchestrator: LayoutPreprocessOrchestrator | None = None,
        workspace_uploads: WorkspaceUploadService | None = None,
    ) -> None:
        self.thread_service = thread_service
        self.workspace_service = workspace_service
        self.artifact_service = artifact_service
        self.task_service = task_service
        self.upload_preprocessor = upload_preprocessor
        self.dataservice = dataservice
        self.preflight_policy = preflight_policy or UploadPreflightPolicy()
        self.thread_uploads = thread_uploads or ThreadUploadService()
        self.preprocess_orchestrator = preprocess_orchestrator or LayoutPreprocessOrchestrator(
            preflight_policy=self.preflight_policy
        )
        self.workspace_uploads = workspace_uploads or WorkspaceUploadService(
            thread_uploads=self.thread_uploads
        )

    async def upload_thread_files(
        self,
        *,
        thread_id: str,
        files: list[UploadFile],
        kind: ThreadUploadKind,
        workspace_id: str | None,
        user_id: str,
    ) -> ThreadUploadResponse:
        self.preflight_policy.validate_file_count(files)
        thread = await self._require_owned_thread(thread_id=thread_id, user_id=user_id)
        resolved_workspace_id = workspace_id or thread.workspace_id
        if workspace_id and thread.workspace_id and workspace_id != thread.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Upload workspace does not match the thread workspace",
            )

        if kind != "transient":
            if not resolved_workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="workspace_id is required for persisted uploads",
                )
            await self._require_owned_workspace(
                workspace_id=resolved_workspace_id,
                user_id=user_id,
            )

        stored_files: list[ThreadAttachment] = []
        refresh_targets: set[str] = set()
        for upload in files:
            attachment = await self._process_upload(
                thread_id=thread_id,
                upload=upload,
                kind=kind,
                resolved_workspace_id=resolved_workspace_id,
                user_id=user_id,
                refresh_targets=refresh_targets,
            )
            stored_files.append(attachment)

        if resolved_workspace_id and refresh_targets:
            await publish_workspace_event(
                resolved_workspace_id,
                "workspace.refresh",
                {"refresh_targets": self._ordered_refresh_targets(refresh_targets)},
            )

        return ThreadUploadResponse(
            success=True,
            files=stored_files,
            message=f"Successfully uploaded {len(stored_files)} file(s)",
        )

    async def _process_upload(
        self,
        *,
        thread_id: str,
        upload: UploadFile,
        kind: ThreadUploadKind,
        resolved_workspace_id: str | None,
        user_id: str,
        refresh_targets: set[str],
    ) -> ThreadAttachment:
        filename, content = await self.preflight_policy.read_content(upload)
        if kind == "literature":
            self.preflight_policy.require_literature_pdf(filename=filename, upload=upload)

        thread_path: Path | None = None
        saved_name = filename
        if kind != "literature":
            thread_path = self.thread_uploads.persist_transient_file(
                thread_id=thread_id,
                filename=filename,
                content=content,
            )
            saved_name = thread_path.name

        reference_id: str | None = None
        artifact_id: str | None = None
        attachment_path: str | None = None
        attachment_url: str | None = None
        metadata: dict[str, object] = {}
        deferred_workspace_context_preprocess = False

        if kind == "literature" and resolved_workspace_id:
            result = await self._import_literature_upload(
                workspace_id=resolved_workspace_id,
                thread_id=thread_id,
                user_id=user_id,
                upload=upload,
                saved_name=saved_name,
                content=content,
                metadata=metadata,
            )
            saved_name = result["saved_name"]
            reference_id = result["reference_id"]
            attachment_path = result["attachment_path"]
            attachment_url = result["attachment_url"]
            refresh_targets.update({"dashboard", "references"})
        else:
            if thread_path is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal upload storage error",
                )
            dispatch = await self.preprocess_orchestrator.preprocess_or_schedule(
                task_service=self.task_service,
                upload_preprocessor=self.upload_preprocessor,
                user_id=user_id,
                workspace_id=resolved_workspace_id,
                thread_id=thread_id,
                filename=saved_name,
                kind=kind,
                content_type=upload.content_type,
                content=content,
                source_path=thread_path,
                output_dir=self.thread_uploads.upload_dir(thread_id) / "_preprocessed" / Path(saved_name).stem,
                output_virtual_root=f"/mnt/user-data/uploads/_preprocessed/{Path(saved_name).stem}",
                is_parseable=self.preflight_policy.is_parseable(
                    filename=upload.filename,
                    content_type=upload.content_type,
                ),
            )
            metadata.update(dispatch.metadata)
            deferred_workspace_context_preprocess = dispatch.deferred_workspace_context_preprocess

        if kind == "workspace_context" and resolved_workspace_id:
            if thread_path is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal upload storage error",
                )
            workspace_result = await self.workspace_uploads.persist_context_upload(
                user_id=user_id,
                workspace_id=resolved_workspace_id,
                thread_id=thread_id,
                upload_filename=upload.filename,
                saved_name=saved_name,
                content_type=upload.content_type,
                content=content,
                thread_path=thread_path,
                metadata=metadata,
                artifact_service=self.artifact_service,
                dataservice=self.dataservice,
                task_service=self.task_service,
                preprocess_orchestrator=self.preprocess_orchestrator,
                deferred_preprocess=deferred_workspace_context_preprocess,
            )
            artifact_id = workspace_result.artifact_id
            refresh_targets.update({"dashboard", "artifacts"})

        return self.thread_uploads.build_attachment(
            thread_id=thread_id,
            filename=saved_name,
            kind=kind,
            content_type=upload.content_type,
            size_bytes=len(content),
            path=attachment_path,
            url=attachment_url,
            reference_id=reference_id,
            artifact_id=artifact_id,
            metadata=metadata,
        )

    async def _import_literature_upload(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
        upload: UploadFile,
        saved_name: str,
        content: bytes,
        metadata: dict[str, object],
    ) -> dict[str, str | None]:
        import_result = await SourceLibraryImportService(self.dataservice).import_uploaded_pdf(
            workspace_id=workspace_id,
            filename=saved_name,
            content_type=upload.content_type,
            content=content,
            task_service=self.task_service,
            user_id=user_id,
            thread_id=thread_id,
        )
        reference = import_result.get("reference")
        asset = import_result.get("asset")
        preprocess = import_result.get("preprocess")
        saved_name = str(import_result.get("filename") or saved_name)
        reference_id: str | None = None
        attachment_url: str | None = None
        if isinstance(reference, dict):
            reference_id = str(reference.get("id") or "") or None
            metadata["reference"] = reference
            metadata["document_title"] = reference.get("title")
            metadata["document_authors"] = reference.get("authors") or []
        if isinstance(asset, dict):
            metadata["reference_asset"] = asset
            metadata["reference_asset_id"] = asset.get("id")
            metadata["stored_path"] = asset.get("file_path")
            metadata["stored_url"] = asset.get("public_url")
            metadata["page_count"] = asset.get("page_count")
            attachment_url = str(asset.get("public_url") or "").strip() or None
        if isinstance(preprocess, dict):
            metadata["preprocess"] = preprocess
        return {
            "saved_name": saved_name,
            "reference_id": reference_id,
            "attachment_path": f"reference://{reference_id}" if reference_id else None,
            "attachment_url": attachment_url,
        }

    async def _require_owned_thread(self, *, thread_id: str, user_id: str) -> Any:
        thread = await self.thread_service.get_thread(thread_id, user_id)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
        return thread

    async def _require_owned_workspace(self, *, workspace_id: str, user_id: str) -> Any:
        workspace = await self.workspace_service.get(workspace_id)
        if workspace is None or not await self.workspace_service.has_active_membership(
            workspace_id=workspace_id,
            user_id=user_id,
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        return workspace

    @staticmethod
    def _ordered_refresh_targets(targets: set[str]) -> list[str]:
        preferred_order = ("dashboard", "references", "artifacts")
        return [target for target in preferred_order if target in targets]
