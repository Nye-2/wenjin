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
    CreditGrantRule,
    CreditGrantRuleType,
    CreditRedeemCode,
    CreditRedemption,
    CreditTransaction,
    CreditTransactionType,
    ExecutionRecord,
    # Generation
    GenerationRecord,
    KnowledgeCategory,
    LatexCompileHistory,
    LatexProject,
    LatexTemplate,
    # Referral
    Referral,
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
    # Models - Artifact
    "Artifact",
    "ArtifactType",
    # Models - Credit
    "CreditTransaction",
    "CreditTransactionType",
    "ComputeSessionRecord",
    "ExecutionRecord",
    # Models - Admin audit
    "AdminLog",
    "AdminActionType",
    # Models - Knowledge
    "UserKnowledge",
    "KnowledgeCategory",
    # Models - Credit Grant Rules
    "CreditGrantRule",
    "CreditGrantRuleType",
    "CreditRedeemCode",
    "CreditRedemption",
    # Models - Referral
    "Referral",
    # Models - Latex
    "LatexProject",
    "LatexTemplate",
    "LatexCompileHistory",
    # Models - Generation
    "GenerationRecord",
    # Models - Task
    "TaskRecord",
    "SubagentTaskRecord",
]
