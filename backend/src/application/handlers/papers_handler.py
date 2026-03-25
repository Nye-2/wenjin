"""Application handler for papers router orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, UploadFile

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
from src.gateway.deps import (
    get_paper_service,
    get_task_service,
    get_workspace_service,
)
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    is_pdf_upload,
    persist_workspace_upload,
    sanitize_upload_filename,
)
from src.task.registry import PAPER_EXTRACTION_TASK
from src.task.service import ConcurrencyLimitError, TaskService

_PERSISTED_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT


class PapersHandler:
    """Request-level orchestration for papers endpoints."""

    def __init__(
        self,
        *,
        paper_service: PaperService,
        workspace_service: WorkspaceService,
        task_service: TaskService,
    ) -> None:
        self.paper_service = paper_service
        self.workspace_service = workspace_service
        self.task_service = task_service

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
        file: UploadFile,
    ) -> dict[str, object]:
        """Upload a PDF and create its initial paper record inside a workspace."""
        await self._require_owned_workspace(
            workspace_id=workspace_id,
            user_id=user_id,
        )

        try:
            filename = sanitize_upload_filename(file.filename)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

        if not is_pdf_upload(filename, file.content_type):
            raise BadRequestError("Only PDF files are accepted")

        content = await file.read()
        if not content:
            raise BadRequestError("Uploaded file is empty")

        size_bytes = len(content)

        try:
            persistent_path = persist_workspace_upload(
                workspace_id=workspace_id,
                bucket="papers",
                filename=filename,
                content=content,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            paper = await self.paper_service.create_in_workspace(
                workspace_id=workspace_id,
                title=Path(persistent_path).stem,
                authors=[],
                file_path=str(persistent_path),
                source="manual_upload",
            )
        except Exception as exc:
            raise BadRequestError(f"Failed to upload paper: {str(exc)}") from exc

        return {
            "success": True,
            "paper_id": str(paper.id),
            "filename": persistent_path.name,
            "original_filename": filename,
            "content_type": file.content_type,
            "size_bytes": size_bytes,
            "workspace_id": workspace_id,
            "file_path": str(persistent_path),
            "source": "manual_upload",
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
            task_id = await self.task_service.submit_task(
                user_id=user_id,
                task_type=PAPER_EXTRACTION_TASK,
                payload={
                    "workspace_id": workspace_id,
                    "paper_id": paper_id,
                    "tier": tier,
                },
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

    async def get_paper_sections(
        self,
        *,
        paper_id: str,
        workspace_id: str | None,
        user_id: str,
    ) -> list[PaperSection]:
        """Get paper sections with optional workspace filtering."""
        paper = await self.paper_service.get(paper_id)
        if paper is None:
            raise NotFoundError(f"Paper not found: {paper_id}")

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


async def get_papers_handler(
    paper_service: PaperService = Depends(get_paper_service),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    task_service: TaskService = Depends(get_task_service),
) -> PapersHandler:
    """Get papers application handler."""
    return PapersHandler(
        paper_service=paper_service,
        workspace_service=workspace_service,
        task_service=task_service,
    )
