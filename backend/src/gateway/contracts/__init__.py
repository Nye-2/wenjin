"""Gateway contracts - shared DTOs, error models, and response schemas."""

from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_response,
    artifact_to_responses,
)
from src.gateway.contracts.error import ErrorDetail, ErrorResponse
from src.gateway.contracts.paper import (
    ExtractionResponse,
    PaperResponse,
    PaperSummaryResponse,
    SectionResponse,
    extraction_to_response,
    paper_to_response,
    paper_to_summary_response,
    section_to_response,
)

__all__ = [
    "ArtifactResponse",
    "ArtifactsListResponse",
    "ErrorDetail",
    "ErrorResponse",
    "ExtractionResponse",
    "PaperResponse",
    "PaperSummaryResponse",
    "SectionResponse",
    "extraction_to_response",
    "artifact_to_response",
    "artifact_to_responses",
    "paper_to_response",
    "paper_to_summary_response",
    "section_to_response",
]
