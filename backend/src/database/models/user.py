"""User model for authentication and ownership."""

from typing import TYPE_CHECKING, List

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .workspace import Workspace
    from .knowledge import UserKnowledge


class User(Base, UUIDMixin, TimestampMixin):
    """User model for authentication and ownership.

    Attributes:
        id: UUID primary key
        email: Unique email address
        name: Display name
        hashed_password: Bcrypt hashed password
        is_active: Whether user account is active
        is_superuser: Whether user has admin privileges
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    knowledge: Mapped[List["UserKnowledge"]] = relationship(
        "UserKnowledge",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
