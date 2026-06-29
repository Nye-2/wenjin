"""User model for authentication and ownership."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .admin_log import AdminLog
    from .credit import CreditTransaction
    from .thread import Thread
    from .workspace import Workspace


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
    credits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
        index=True,
    )
    reserved_credits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_credits_earned: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_credits_spent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    refresh_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspaces: Mapped[list["Workspace"]] = relationship(
        "Workspace",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    threads: Mapped[list["Thread"]] = relationship(
        "Thread",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(
        "CreditTransaction",
        back_populates="user",
        foreign_keys="CreditTransaction.user_id",
        cascade="all, delete-orphan",
    )
    admin_logs: Mapped[list["AdminLog"]] = relationship(
        "AdminLog",
        back_populates="admin",
        foreign_keys="AdminLog.admin_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
