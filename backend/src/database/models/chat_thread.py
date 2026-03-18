"""Chat thread model for persisted conversations."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .user import User
    from .workspace import Workspace


MESSAGES_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class ChatThread(Base, UUIDMixin, TimestampMixin):
    """Persisted chat thread scoped to a user and optional workspace."""

    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("ix_chat_threads_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        server_default="default",
    )
    messages: Mapped[list[dict[str, Any]]] = mapped_column(
        MESSAGES_JSON_TYPE,
        nullable=False,
        default=list,
        server_default="[]",
    )

    user: Mapped["User"] = relationship("User", back_populates="chat_threads")
    workspace: Mapped["Workspace | None"] = relationship(
        "Workspace",
        back_populates="chat_threads",
    )

    def __repr__(self) -> str:
        return (
            f"<ChatThread(id={self.id}, user_id={self.user_id}, "
            f"workspace_id={self.workspace_id})>"
        )
