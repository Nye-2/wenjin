"""Database package initialization.

This package provides:
- SQLAlchemy ORM models for PostgreSQL
- Async session management
- pgvector support for embeddings
"""

from .base import Base, TimestampMixin, UUIDMixin, generate_uuid
from .session import (
    get_db_session,
    async_session_factory,
    engine,
    init_db,
    close_db,
)

from .models import (
    # User
    User,
    # Workspace
    Workspace,
    WorkspaceType,
    # Paper
    Paper,
    WorkspacePaper,
    PaperExtraction,
    PaperChunk,
    PaperSection,
    # Artifact
    Artifact,
    ArtifactType,
    # Knowledge
    UserKnowledge,
    KnowledgeCategory,
    # Generation
    GenerationRecord,
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
    # Models - Knowledge
    "UserKnowledge",
    "KnowledgeCategory",
    # Models - Generation
    "GenerationRecord",
]
