"""Academic module for literature management, knowledge storage, and citation handling."""

from src.database import (
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
