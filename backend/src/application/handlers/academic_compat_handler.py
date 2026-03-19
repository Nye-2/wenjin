"""Compatibility handler for deprecated academic router endpoints."""

from __future__ import annotations

from fastapi import UploadFile

from src.academic.services import ArtifactService
from src.academic.services.paper_service import PaperService
from src.application.errors import BadRequestError, InternalServiceError


class AcademicCompatHandler:
    """Request-level orchestration for deprecated academic endpoints."""

    def __init__(
        self,
        *,
        paper_service: PaperService,
        artifact_service: ArtifactService | None = None,
    ) -> None:
        self.paper_service = paper_service
        self.artifact_service = artifact_service

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
        workspace_id: str | None,
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

        paper = await self.paper_service.create(
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

    async def list_artifacts(
        self,
        *,
        workspace_id: str,
        artifact_type: str | None,
    ) -> list[object]:
        """List artifacts for a workspace via the compatibility surface."""
        self._require_artifact_service()
        return await self.artifact_service.list_by_workspace(  # type: ignore[union-attr]
            workspace_id=workspace_id,
            type=artifact_type,
        )

    async def create_artifact(
        self,
        *,
        workspace_id: str,
        request,
    ) -> object:
        """Create an artifact via the compatibility surface."""
        self._require_artifact_service()
        return await self.artifact_service.create(  # type: ignore[union-attr]
            workspace_id=workspace_id,
            type=request.type,
            title=request.title,
            content=request.content,
            created_by_skill=request.created_by_skill,
            parent_artifact_id=request.parent_artifact_id,
        )

    async def get_artifact(self, artifact_id: str) -> object | None:
        """Get an artifact by id via the compatibility surface."""
        self._require_artifact_service()
        return await self.artifact_service.get(artifact_id)  # type: ignore[union-attr]

    async def get_artifact_lineage(self, artifact_id: str) -> list[object]:
        """Get artifact lineage via the compatibility surface."""
        self._require_artifact_service()
        return await self.artifact_service.get_lineage(artifact_id)  # type: ignore[union-attr]

    def _require_artifact_service(self) -> None:
        if self.artifact_service is None:
            raise InternalServiceError("artifact_service is required for artifact compatibility operations")
