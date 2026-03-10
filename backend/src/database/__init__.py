"""Database package initialization.

This package provides:
- SQLAlchemy ORM models for PostgreSQL
- Async session management
- pgvector support for embeddings
"""

from .base import Base, TimestampMixin, UUIDMixin, generate_uuid
from .models import (
    # Artifact
    Artifact,
    ArtifactType,
    # Citation
    Citation,
    CitationType,
    # Generation
    GenerationRecord,
    KnowledgeCategory,
    # Paper
    Paper,
    PaperChunk,
    PaperExtraction,
    PaperSection,
    # User
    User,
    # Knowledge
    UserKnowledge,
    # Workspace
    Workspace,
    WorkspacePaper,
    WorkspaceType,
)
from .session import (
    async_session_factory,
    close_db,
    engine,
    get_db_session,
    init_db,
)

__all__ = [
    # Base and utilities
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "generate_uuid",
    # Session management
    "get_db_session",
    "async_session_factory",
    "engine",
    "init_db",
    "close_db",
    # Models - User
    "User",
    # Models - Workspace
    "Workspace",
    "WorkspaceType",
    # Models - Paper
    "Paper",
    "WorkspacePaper",
    "PaperExtraction",
    "PaperChunk",
    "PaperSection",
    # Models - Artifact
    "Artifact",
    "ArtifactType",
    # Models - Citation
    "Citation",
    "CitationType",
    # Models - Knowledge
    "UserKnowledge",
    "KnowledgeCategory",
    # Models - Generation
    "GenerationRecord",
]
