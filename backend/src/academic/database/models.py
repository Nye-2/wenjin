"""Compatibility re-exports for legacy academic database model imports."""

from src.database import (
    Artifact,
    GenerationRecord,
    Paper,
    PaperChunk,
    PaperExtraction,
    PaperSection,
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
    "PaperSection",
    "Artifact",
    "UserKnowledge",
    "GenerationRecord",
]
