"""Compatibility handler for deprecated academic router endpoints."""

from __future__ import annotations

from fastapi import UploadFile

from src.academic.services.paper_service import PaperService
from src.application.errors import BadRequestError


class AcademicCompatHandler:
    """Request-level orchestration for deprecated academic endpoints."""

    def __init__(
        self,
        *,
        paper_service: PaperService,
    ) -> None:
        self.paper_service = paper_service

    async def create_paper(self, request) -> object:
        """Create a paper using the compatibility request payload."""
        return await self.paper_service.create(
            doi=request.doi,
            title=request.title,
            authors=request.authors,
            year=request.year,
            venue=request.venue,
            abstract=request.abstract,
        )

    async def upload_paper(
        self,
        *,
        file: UploadFile,
        workspace_id: str,
    ) -> dict[str, object]:
        """Upload a paper PDF and create a minimal paper record."""
        if file.content_type not in ("application/pdf", "application/x-pdf"):
            raise BadRequestError("Only PDF files are accepted")

        content = await file.read()
        if not content:
            raise BadRequestError("Uploaded file is empty")

        size_bytes = len(content)
        filename = file.filename or "untitled.pdf"
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        paper = await self.paper_service.create_in_workspace(
            workspace_id=workspace_id,
            title=title,
            authors=[],
            source="upload",
        )

        return {
            "success": True,
            "paper_id": paper.id,
            "filename": filename,
            "content_type": file.content_type,
            "size_bytes": size_bytes,
            "workspace_id": workspace_id,
        }

    async def search_papers(
        self,
        *,
        query: str,
        limit: int,
    ) -> dict[str, str]:
        """Search papers via the legacy Semantic Scholar compatibility endpoint."""
        from src.academic.tools.semantic_scholar import semantic_scholar_search_tool

        result = await semantic_scholar_search_tool.ainvoke(
            {
                "query": query,
                "limit": limit,
            }
        )
        return {"result": result}
