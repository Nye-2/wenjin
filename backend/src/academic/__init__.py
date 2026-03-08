"""Academic module for literature management, knowledge storage, and citation handling."""

from .database.models import (
    Workspace,
    Paper,
    WorkspacePaper,
    PaperExtraction,
    PaperChunk,
    Artifact,
    UserKnowledge,
    GenerationRecord,
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
