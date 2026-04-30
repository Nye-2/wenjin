"""Gateway contracts - shared DTOs, error models, and response schemas."""

from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_response,
    artifact_to_responses,
)
from src.gateway.contracts.error import ErrorDetail, ErrorResponse

__all__ = [
    "ArtifactResponse",
    "ArtifactsListResponse",
    "ErrorDetail",
    "ErrorResponse",
    "artifact_to_response",
    "artifact_to_responses",
]
