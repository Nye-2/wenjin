"""Academic module for literature management, knowledge storage, and citation handling."""

from src.database import (
    Artifact,
    GenerationRecord,
    ReferenceAsset,
    ReferenceOutlineNode,
    ReferenceTextUnit,
    UserKnowledge,
    Workspace,
    WorkspaceReference,
)

__all__ = [
    "Workspace",
    "WorkspaceReference",
    "ReferenceAsset",
    "ReferenceOutlineNode",
    "ReferenceTextUnit",
    "Artifact",
    "UserKnowledge",
    "GenerationRecord",
]
