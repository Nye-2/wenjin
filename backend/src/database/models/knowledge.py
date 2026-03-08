"""UserKnowledge model for cross-workspace personalization."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Float, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from ..base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class KnowledgeCategory(str, enum.Enum):
    """Categories of user knowledge."""
    PREFERENCE = "preference"      # User preferences (citation style, writing tone)
    KNOWLEDGE = "knowledge"        # Domain knowledge
    CONTEXT = "context"            # Contextual information
    BEHAVIOR = "behavior"          # Observed behaviors
    GOAL = "goal"                  # User goals


class UserKnowledge(Base, UUIDMixin, TimestampMixin):
    """UserKnowledge model for cross-workspace personalization.

    Stores user-specific information that persists across all workspaces.
    Similar to DeerFlow's memory system with confidence scoring.

    Attributes:
        id: UUID primary key
        user_id: Foreign key to user
        category: Knowledge category
        content: Knowledge content
        confidence: Confidence score (0.0 to 1.0)
        source: Source of this knowledge (skill_name, manual, etc.)
        workspace_context: Optional workspace_id if knowledge is workspace-specific
        is_active: Whether this knowledge is active
    """

    __tablename__ = "user_knowledge"
    __table_args__ = (
        Index("ix_user_knowledge_user_category", "user_id", "category"),
        Index("ix_user_knowledge_confidence", "confidence"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[KnowledgeCategory] = mapped_column(
        SQLEnum(KnowledgeCategory),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.7,
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    workspace_context: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="knowledge")

    def __repr__(self) -> str:
        return f"<UserKnowledge(id={self.id}, category={self.category}, user={self.user_id})>"

    def boost_confidence(self, amount: float = 0.1) -> None:
        """Increase confidence score."""
        self.confidence = min(1.0, self.confidence + amount)

    def decay_confidence(self, amount: float = 0.05) -> None:
        """Decrease confidence score."""
        self.confidence = max(0.0, self.confidence - amount)
