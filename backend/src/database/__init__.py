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
    # Credit
    ComputeSessionRecord,
    CreditTransaction,
    CreditTransactionType,
    # Generation
    ExecutionSessionRecord,
    GenerationRecord,
    KnowledgeCategory,
    LatexCompileHistory,
    LatexProject,
    LatexTemplate,
    ReferenceAcceptedStatus,
    ReferenceAsset,
    ReferenceAssetType,
    ReferenceBibtexScope,
    ReferenceBibtexSnapshot,
    ReferenceEvidenceLevel,
    ReferenceExternalId,
    ReferenceFulltextStatus,
    ReferenceLibraryStatus,
    ReferenceOutlineNode,
    ReferencePreprocessStatus,
    ReferenceReadStatus,
    ReferenceSourceType,
    ReferenceTextUnit,
    ReferenceTextUnitType,
    ReferenceUsageEvent,
    ReferenceUsageType,
    SubagentTaskRecord,
    # Task
    TaskRecord,
    Thread,
    # User
    User,
    # Knowledge
    UserKnowledge,
    # Workspace
    Workspace,
    WorkspaceReference,
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
    # Models - Thread
    "Thread",
    # Models - Reference Library
    "WorkspaceReference",
    "ReferenceExternalId",
    "ReferenceAsset",
    "ReferenceOutlineNode",
    "ReferenceTextUnit",
    "ReferenceUsageEvent",
    "ReferenceBibtexSnapshot",
    "ReferenceSourceType",
    "ReferenceLibraryStatus",
    "ReferenceEvidenceLevel",
    "ReferenceFulltextStatus",
    "ReferenceReadStatus",
    "ReferenceAssetType",
    "ReferencePreprocessStatus",
    "ReferenceTextUnitType",
    "ReferenceUsageType",
    "ReferenceAcceptedStatus",
    "ReferenceBibtexScope",
    # Models - Artifact
    "Artifact",
    "ArtifactType",
    # Models - Credit
    "CreditTransaction",
    "CreditTransactionType",
    "ComputeSessionRecord",
    # Models - Admin audit
    "AdminLog",
    "AdminActionType",
    # Models - Knowledge
    "UserKnowledge",
    "KnowledgeCategory",
    # Models - Latex
    "LatexProject",
    "LatexTemplate",
    "LatexCompileHistory",
    # Models - Generation
    "GenerationRecord",
    "ExecutionSessionRecord",
    # Models - Task
    "TaskRecord",
    "SubagentTaskRecord",
]
