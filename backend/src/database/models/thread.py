"""Thread model for persisted conversations."""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .user import User
    from .workspace import Workspace


class Thread(Base, UUIDMixin, TimestampMixin):
    """Persisted thread scoped to a user and optional workspace."""

    __tablename__ = "threads"
    __table_args__ = (
        Index("ix_threads_user_updated", "user_id", "updated_at"),
        Index("ix_threads_user_workspace_updated", "user_id", "workspace_id", "updated_at"),
        CheckConstraint(
            "message_count >= 0",
            name="ck_threads_message_count_non_negative",
        ),
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
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_message_preview: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_message_role: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    user: Mapped["User"] = relationship("User", back_populates="threads")
    workspace: Mapped["Workspace | None"] = relationship(
        "Workspace",
        back_populates="threads",
        foreign_keys=[workspace_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Thread(id={self.id}, user_id={self.user_id}, "
            f"workspace_id={self.workspace_id})>"
        )
