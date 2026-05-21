"""Academic module for literature management, knowledge storage, and citation handling."""

from src.database import (
    Artifact,
    GenerationRecord,
    UserKnowledge,
    Workspace,
)

__all__ = [
    "Workspace",
    "Artifact",
    "UserKnowledge",
    "GenerationRecord",
]
