"""Shared paper response contracts and serializers."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from src.services.workspace_uploads import workspace_upload_public_url


class PaperSummaryResponse(BaseModel):
    """Common paper response fields shared by multiple routers."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    doi: str | None
    title: str
    authors: list[dict]
    year: int | None
    venue: str | None
    abstract: str | None
    source: str
    citation_count: int | None
    reference_count: int | None
    file_url: str | None = None


class PaperResponse(PaperSummaryResponse):
    """Detailed paper response for the canonical papers router."""

    external_ids: dict
    toc: list | None


class SectionResponse(BaseModel):
    """Detailed paper section response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: str
    workspace_id: str
    section_title: str
    section_path: str
    page_start: int
    page_end: int
    content: str
    level: int


class PaperExtractionTaskResponse(BaseModel):
    """Async paper extraction submission response."""

    task_id: str
    status: str = "pending"
    paper_id: str
    workspace_id: str
    tier: int
    message: str
    reused_existing_task: bool = False


def _paper_summary_payload(
    paper: Any,
    *,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    file_url = None
    if workspace_id and getattr(paper, "file_path", None):
        try:
            file_url = workspace_upload_public_url(workspace_id, paper.file_path)
        except ValueError:
            file_url = None

    return {
        "id": str(paper.id),
        "doi": paper.doi,
        "title": paper.title,
        "authors": paper.authors or [],
        "year": paper.year,
        "venue": paper.venue,
        "abstract": paper.abstract,
        "source": paper.source,
        "citation_count": paper.citation_count,
        "reference_count": paper.reference_count,
        "file_url": file_url,
    }


def paper_to_summary_response(
    paper: Any,
    *,
    workspace_id: str | None = None,
) -> PaperSummaryResponse:
    """Convert a paper object into the shared summary response model."""
    return PaperSummaryResponse(
        **_paper_summary_payload(paper, workspace_id=workspace_id)
    )


def paper_to_response(
    paper: Any,
    *,
    workspace_id: str | None = None,
) -> PaperResponse:
    """Convert a paper object into the detailed papers-router response model."""
    payload = _paper_summary_payload(paper, workspace_id=workspace_id)
    payload.update(
        {
            "external_ids": paper.external_ids or {},
            "toc": paper.toc,
        }
    )
    return PaperResponse(**payload)


def section_to_response(section: Any) -> SectionResponse:
    """Convert a paper section object into the shared response model."""
    return SectionResponse(
        id=str(section.id),
        paper_id=str(section.paper_id),
        workspace_id=str(section.workspace_id),
        section_title=section.section_title,
        section_path=section.section_path,
        page_start=section.page_start,
        page_end=section.page_end,
        content=section.content,
        level=section.level,
    )


def paper_extraction_task_to_response(result: Any) -> PaperExtractionTaskResponse:
    """Convert a paper extraction task submission result into the shared response model."""
    return PaperExtractionTaskResponse(
        task_id=str(result.task_id),
        paper_id=str(result.paper_id),
        workspace_id=str(result.workspace_id),
        tier=int(result.tier),
        message=str(result.message),
        reused_existing_task=bool(getattr(result, "reused_existing_task", False)),
    )
