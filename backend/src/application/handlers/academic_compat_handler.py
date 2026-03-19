"""Compatibility handler for deprecated academic router endpoints."""

from __future__ import annotations

from src.academic.services.paper_service import PaperService


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
