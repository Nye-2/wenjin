"""Database package initialization.

This package provides:
- SQLAlchemy ORM models for PostgreSQL
- Async session management
- pgvector support for embeddings
"""

from .base import Base, TimestampMixin, UUIDMixin, generate_uuid
from .models import (
    AdminActionType,
    AdminLog,
    # Artifact
    Artifact,
    ArtifactType,
    ChatThread,
    # Citation
    Citation,
    CitationType,
    # Credit
    CreditTransaction,
    CreditTransactionType,
    # Generation
    GenerationRecord,
    KnowledgeCategory,
    # Paper
    Paper,
    PaperChunk,
    PaperExtraction,
    PaperSection,
    SubagentTaskRecord,
    # Task
    TaskRecord,
    # User
    User,
    # Knowledge
    UserKnowledge,
    # Workspace
    Workspace,
    # Workspace Literature
    WorkspaceLiterature,
    WorkspacePaper,
    WorkspaceType,
)
from .session import (
    async_session_factory,
    close_db,
    engine,
    get_async_session_factory,
    get_db_session,
    get_engine,
    init_db,
    reset_db_engine,
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
    "get_async_session_factory",
    "get_engine",
    "init_db",
    "close_db",
    "reset_db_engine",
    # Models - User
    "User",
    # Models - Workspace
    "Workspace",
    "WorkspaceType",
    # Models - Chat
    "ChatThread",
    # Models - Paper
    "Paper",
    "WorkspacePaper",
    "PaperExtraction",
    "PaperChunk",
    "PaperSection",
    # Models - Artifact
    "Artifact",
    "ArtifactType",
    # Models - Credit
    "CreditTransaction",
    "CreditTransactionType",
    # Models - Admin audit
    "AdminLog",
    "AdminActionType",
    # Models - Citation
    "Citation",
    "CitationType",
    # Models - Knowledge
    "UserKnowledge",
    "KnowledgeCategory",
    # Models - Generation
    "GenerationRecord",
    # Models - Task
    "TaskRecord",
    "SubagentTaskRecord",
    # Models - Workspace Literature
    "WorkspaceLiterature",
]
