"""Gateway contracts - shared DTOs, error models, and response schemas."""

from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_response,
    artifact_to_responses,
)
from src.gateway.contracts.error import ErrorDetail, ErrorResponse
from src.gateway.contracts.paper import (
    PaperResponse,
    PaperExtractionTaskResponse,
    PaperSummaryResponse,
    SectionResponse,
    paper_to_response,
    paper_extraction_task_to_response,
    paper_to_summary_response,
    section_to_response,
)

__all__ = [
    "ArtifactResponse",
    "ArtifactsListResponse",
    "ErrorDetail",
    "ErrorResponse",
    "PaperResponse",
    "PaperExtractionTaskResponse",
    "PaperSummaryResponse",
    "SectionResponse",
    "artifact_to_response",
    "artifact_to_responses",
    "paper_to_response",
    "paper_extraction_task_to_response",
    "paper_to_summary_response",
    "section_to_response",
]
