"""Application handler for papers router orchestration."""

from __future__ import annotations

from typing import Any

from fastapi import Depends
from fastapi import UploadFile

from src.academic.services.extraction_service import ExtractionService
from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.application.errors import (
    AccessDeniedError,
    BadRequestError,
    InternalServiceError,
    NotFoundError,
)
from src.database import Paper, PaperExtraction, PaperSection
from src.gateway.deps import (
    get_extraction_service,
    get_paper_service,
    get_workspace_service,
)


class PapersHandler:
    """Request-level orchestration for papers endpoints."""

    def __init__(
        self,
        *,
        paper_service: PaperService,
        extraction_service: ExtractionService,
        workspace_service: WorkspaceService,
    ) -> None:
        self.paper_service = paper_service
        self.extraction_service = extraction_service
        self.workspace_service = workspace_service

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

        if file.content_type not in ("application/pdf", "application/x-pdf"):
            raise BadRequestError("Only PDF files are accepted")

        content = await file.read()
        if not content:
            raise BadRequestError("Uploaded file is empty")

        size_bytes = len(content)
        filename = file.filename or "untitled.pdf"
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        try:
            paper = await self.paper_service.create_in_workspace(
                workspace_id=workspace_id,
                title=title,
                authors=[],
                source="upload",
            )
        except Exception as exc:
            raise BadRequestError(f"Failed to upload paper: {str(exc)}") from exc

        return {
            "success": True,
            "paper_id": str(paper.id),
            "filename": filename,
            "content_type": file.content_type,
            "size_bytes": size_bytes,
            "workspace_id": workspace_id,
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
    ) -> PaperExtraction:
        """Trigger extraction for a paper in a workspace."""
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

        try:
            extraction = await self.extraction_service.extract_paper(
                paper_id=paper_id,
                file_path=paper.file_path,
                tier=tier,
            )
            await self.extraction_service.extract_sections(
                paper_id=paper_id,
                workspace_id=workspace_id,
                file_path=paper.file_path,
            )
            return extraction
        except Exception as exc:
            raise InternalServiceError(f"Extraction failed: {str(exc)}") from exc

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
    extraction_service: ExtractionService = Depends(get_extraction_service),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> PapersHandler:
    """Get papers application handler."""
    return PapersHandler(
        paper_service=paper_service,
        extraction_service=extraction_service,
        workspace_service=workspace_service,
    )
