"""Academic module for literature management, knowledge storage, and citation handling."""

from .database.models import (
    Artifact,
    GenerationRecord,
    Paper,
    PaperChunk,
    PaperExtraction,
    UserKnowledge,
    Workspace,
    WorkspacePaper,
)

__all__ = [
    "Workspace",
    "Paper",
    "WorkspacePaper",
    "PaperExtraction",
    "PaperChunk",
    "Artifact",
    "UserKnowledge",
    "GenerationRecord",
]
