"""Application handler for papers router orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.application.errors import (
    AccessDeniedError,
    BadRequestError,
    InternalServiceError,
    NotFoundError,
)
from src.application.results import PaperExtractionTaskSubmission
from src.database import Paper, PaperSection
from src.services.upload_preprocessor import UploadPreprocessor
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    extract_document_preview,
    is_pdf_upload,
    persist_workspace_upload,
    sanitize_upload_filename,
    workspace_upload_public_url,
)
from src.task.registry import PAPER_EXTRACTION_TASK
from src.task.service import ConcurrencyLimitError, TaskService

_PERSISTED_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UploadedPaperPayload:
    """Transport-agnostic uploaded paper content."""

    filename: str | None
    content_type: str | None
    content: bytes


class PapersHandler:
    """Request-level orchestration for papers endpoints."""

    def __init__(
        self,
        *,
        paper_service: PaperService,
        workspace_service: WorkspaceService,
        task_service: TaskService,
        upload_preprocessor: UploadPreprocessor | None = None,
    ) -> None:
        self.paper_service = paper_service
        self.workspace_service = workspace_service
        self.task_service = task_service
        self.upload_preprocessor = upload_preprocessor

    async def create_paper(
        self,
        request: Any,
        *,
        user_id: str,
    ) -> Paper:
        """Create a paper from request payload."""
        await self._require_owned_workspace(
            workspace_id=request.workspace_id,
            user_id=user_id,
        )

        try:
            return await self.paper_service.create_in_workspace(
                workspace_id=request.workspace_id,
                doi=request.doi,
                title=request.title,
                authors=request.authors,
                year=request.year,
                venue=request.venue,
                abstract=request.abstract,
                file_path=request.file_path,
                source=request.source,
                external_ids=request.external_ids,
                citation_count=request.citation_count,
                reference_count=request.reference_count,
            )
        except Exception as exc:
            raise BadRequestError(f"Failed to create paper: {str(exc)}") from exc

    async def upload_paper(
        self,
        *,
        workspace_id: str,
        user_id: str,
        upload: UploadedPaperPayload,
    ) -> dict[str, object]:
        """Upload a PDF and create its initial paper record inside a workspace."""
        await self._require_owned_workspace(
            workspace_id=workspace_id,
            user_id=user_id,
        )

        try:
            filename = sanitize_upload_filename(upload.filename)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

        if not is_pdf_upload(filename, upload.content_type):
            raise BadRequestError("Only PDF files are accepted")

        content = upload.content
        if not content:
            raise BadRequestError("Uploaded file is empty")

        size_bytes = len(content)
        preprocess_metadata: dict[str, object] | None = None

        try:
            document_preview = extract_document_preview(
                filename,
                upload.content_type,
                content=content,
            )
            preview_authors = document_preview.get("authors")
            author_names = preview_authors if isinstance(preview_authors, list) else []
            persistent_path = persist_workspace_upload(
                workspace_id=workspace_id,
                bucket="papers",
                filename=filename,
                content=content,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            if self.upload_preprocessor is not None:
                preprocess_result = await self.upload_preprocessor.preprocess_file(
                    filename=filename,
                    content_type=upload.content_type,
                    content=content,
                    output_dir=(
                        persistent_path.parent
                        / "_preprocessed"
                        / persistent_path.stem
                    ),
                )
                preprocess_metadata = preprocess_result.to_metadata()
                for key in (
                    "markdown_paths",
                    "markdown_image_paths",
                    "output_image_paths",
                ):
                    values = preprocess_metadata.get(key)
                    if not isinstance(values, list):
                        continue
                    urls: list[str] = []
                    for value in values:
                        if not isinstance(value, str):
                            continue
                        try:
                            public_url = workspace_upload_public_url(
                                workspace_id,
                                value,
                                root=_PERSISTED_UPLOAD_ROOT,
                            )
                        except ValueError:
                            continue
                        if public_url:
                            urls.append(public_url)
                    if urls:
                        preprocess_metadata[f"{key.removesuffix('_paths')}_urls"] = urls
                manifest_path = preprocess_metadata.get("manifest_path")
                if isinstance(manifest_path, str) and manifest_path.strip():
                    try:
                        manifest_url = workspace_upload_public_url(
                            workspace_id,
                            manifest_path,
                            root=_PERSISTED_UPLOAD_ROOT,
                        )
                    except ValueError:
                        manifest_url = None
                    if manifest_url:
                        preprocess_metadata["manifest_url"] = manifest_url
        except Exception as exc:
            raise BadRequestError(f"Failed to process upload: {str(exc)}") from exc

        paper = None
        try:
            paper = await self.paper_service.create_in_workspace(
                workspace_id=workspace_id,
                title=(
                    str(document_preview.get("title") or "").strip()
                    or Path(persistent_path).stem
                ),
                authors=[
                    {"name": name}
                    for name in author_names
                    if isinstance(name, str) and name.strip()
                ],
                file_path=str(persistent_path),
                source="manual_upload",
            )
            extraction = await self.schedule_uploaded_paper_extraction(
                paper_id=str(paper.id),
                workspace_id=workspace_id,
                user_id=user_id,
                tier=1,
            )
        except Exception as exc:
            # Clean up orphaned file on DB/queue failure
            try:
                if persistent_path and persistent_path.is_file():
                    persistent_path.unlink()
                    logger.info("Cleaned up orphaned upload: %s", persistent_path)
            except OSError:
                logger.warning("Failed to clean up orphaned file: %s", persistent_path, exc_info=True)
            raise BadRequestError(f"Failed to upload paper: {str(exc)}") from exc

        return {
            "success": True,
            "paper_id": str(paper.id),
            "filename": persistent_path.name,
            "original_filename": filename,
            "content_type": upload.content_type,
            "size_bytes": size_bytes,
            "workspace_id": workspace_id,
            "file_path": str(persistent_path),
            "file_url": workspace_upload_public_url(
                workspace_id,
                persistent_path,
                root=_PERSISTED_UPLOAD_ROOT,
            ),
            "source": "manual_upload",
            "extraction": extraction,
            "preprocess": preprocess_metadata,
        }

    async def list_papers(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[Paper]:
        """List papers visible to a user."""
        if workspace_id:
            await self._require_owned_workspace(workspace_id=workspace_id, user_id=user_id)
            papers = await self.paper_service.list_workspace_papers(workspace_id)
            return papers[:limit]

        return await self.paper_service.list_visible_to_user(user_id, limit=limit)

    async def get_paper(
        self,
        *,
        paper_id: str,
        user_id: str,
    ) -> Paper:
        """Get a paper with owner-scoped visibility checks."""
        return await self._get_accessible_paper_or_404(paper_id=paper_id, user_id=user_id)

    async def update_paper(
        self,
        *,
        paper_id: str,
        user_id: str,
        request: Any,
    ) -> Paper:
        """Update a paper after enforcing visibility."""
        await self._get_accessible_paper_or_404(
            paper_id=paper_id,
            user_id=user_id,
        )

        updated = await self.paper_service.update(
            paper_id,
            **request.model_dump(exclude_unset=True),
        )
        if updated is None:
            raise NotFoundError(f"Paper not found: {paper_id}")
        return updated

    async def delete_paper(
        self,
        *,
        paper_id: str,
        user_id: str,
    ) -> None:
        """Delete a paper after enforcing visibility."""
        await self._get_accessible_paper_or_404(
            paper_id=paper_id,
            user_id=user_id,
        )

        deleted = await self.paper_service.delete(paper_id)
        if not deleted:
            raise NotFoundError(f"Paper not found: {paper_id}")

    async def extract_paper(
        self,
        *,
        paper_id: str,
        workspace_id: str,
        tier: int,
        user_id: str,
    ) -> PaperExtractionTaskSubmission:
        """Queue extraction for a paper in a workspace."""
        paper = await self._get_accessible_paper_or_404(paper_id=paper_id, user_id=user_id)

        await self._require_owned_workspace(workspace_id=workspace_id, user_id=user_id)
        in_workspace = await self.paper_service.is_in_workspace(
            paper_id=paper_id,
            workspace_id=workspace_id,
        )
        if not in_workspace:
            raise NotFoundError("Paper not found in workspace")

        if not paper.file_path:
            raise BadRequestError("Paper has no file path for extraction")

        return await self._queue_paper_extraction_submission(
            paper_id=paper_id,
            workspace_id=workspace_id,
            user_id=user_id,
            tier=tier,
        )

    async def _queue_paper_extraction_submission(
        self,
        *,
        paper_id: str,
        workspace_id: str,
        user_id: str,
        tier: int,
        thread_id: str | None = None,
    ) -> PaperExtractionTaskSubmission:
        """Submit or reuse a paper extraction task after access checks are satisfied."""
        existing_task_id = await self.task_service.find_active_task_by_payload(
            user_id=user_id,
            task_type=PAPER_EXTRACTION_TASK,
            payload_filters={
                "workspace_id": workspace_id,
                "paper_id": paper_id,
                "tier": tier,
            },
        )
        if existing_task_id:
            return PaperExtractionTaskSubmission(
                task_id=existing_task_id,
                paper_id=paper_id,
                workspace_id=workspace_id,
                tier=tier,
                message="已有进行中的论文提取任务",
                reused_existing_task=True,
            )

        try:
            payload = {
                "workspace_id": workspace_id,
                "paper_id": paper_id,
                "tier": tier,
            }
            if thread_id:
                payload["thread_id"] = thread_id
            task_id = await self.task_service.submit_task(
                user_id=user_id,
                task_type=PAPER_EXTRACTION_TASK,
                payload=payload,
            )
        except ConcurrencyLimitError as exc:
            raise BadRequestError(
                f"并发任务数已达上限（{exc.limit}），请等待现有任务完成"
            ) from exc
        except Exception as exc:
            raise InternalServiceError(
                f"Failed to queue extraction: {str(exc)}"
            ) from exc
        return PaperExtractionTaskSubmission(
            task_id=task_id,
            paper_id=paper_id,
            workspace_id=workspace_id,
            tier=tier,
            message="论文提取任务已提交",
        )

    async def schedule_uploaded_paper_extraction(
        self,
        *,
        paper_id: str,
        workspace_id: str,
        user_id: str,
        tier: int = 1,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Best-effort extraction scheduling for newly uploaded papers.

        Upload should succeed even if background extraction cannot be queued.
        """
        try:
            submission = await self._queue_paper_extraction_submission(
                paper_id=paper_id,
                workspace_id=workspace_id,
                user_id=user_id,
                tier=tier,
                thread_id=thread_id,
            )
            payload = submission.to_dict()
            payload["status"] = (
                "existing" if submission.reused_existing_task else "scheduled"
            )
            return payload
        except Exception as exc:
            logger.warning(
                "Failed to auto-schedule paper extraction for paper %s in workspace %s: %s",
                paper_id,
                workspace_id,
                exc,
                exc_info=True,
            )
            return {
                "status": "failed",
                "message": str(exc),
                "paper_id": paper_id,
                "workspace_id": workspace_id,
                "tier": tier,
            }

    async def get_paper_sections(
        self,
        *,
        paper_id: str,
        workspace_id: str | None,
        user_id: str,
    ) -> list[PaperSection]:
        """Get paper sections with optional workspace filtering."""
        # Always verify user has access to this paper
        await self._get_accessible_paper_or_404(paper_id=paper_id, user_id=user_id)

        if workspace_id:
            await self._require_owned_workspace(workspace_id=workspace_id, user_id=user_id)
            return await self.paper_service.list_sections(
                paper_id=paper_id,
                workspace_id=workspace_id,
            )

        return await self.paper_service.list_sections(
            paper_id=paper_id,
            user_id=user_id,
        )

    async def search_papers(
        self,
        *,
        request: Any,
        user_id: str,
    ) -> dict[str, Any]:
        """Search papers with optional workspace scoping."""
        if request.workspace_id:
            await self._require_owned_workspace(
                workspace_id=request.workspace_id,
                user_id=user_id,
            )
            papers = await self.paper_service.search(
                query=request.query,
                workspace_id=request.workspace_id,
                limit=request.limit,
            )
        else:
            papers = await self.paper_service.search_visible_to_user(
                user_id=user_id,
                query=request.query,
                limit=request.limit,
            )

        return {
            "query": request.query,
            "count": len(papers),
            "papers": papers,
        }

    async def _get_accessible_paper_or_404(
        self,
        *,
        paper_id: str,
        user_id: str,
    ) -> Paper:
        """Load a paper and enforce workspace-based visibility."""
        paper = await self.paper_service.get(paper_id)
        if paper is None:
            raise NotFoundError(f"Paper not found: {paper_id}")

        accessible = await self.paper_service.is_accessible_by_user(
            paper_id=paper_id,
            user_id=user_id,
        )
        if not accessible:
            raise NotFoundError(f"Paper not found: {paper_id}")
        return paper

    async def _require_owned_workspace(self, *, workspace_id: str, user_id: str) -> None:
        """Ensure workspace exists and is owned by the current user."""
        workspace = await self.workspace_service.get(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        if str(workspace.user_id) != user_id:
            raise AccessDeniedError("Access denied")
