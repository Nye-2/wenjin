"""Admin audit log model."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDMixin

if TYPE_CHECKING:
    from .user import User


class AdminActionType(StrEnum):
    """Supported admin action types."""

    CREDIT_GRANT = "credit_grant"
    CREDIT_DEDUCT = "credit_deduct"
    USER_ROLE_CHANGE = "user_role_change"
    USER_STATUS_CHANGE = "user_status_change"
    CAPABILITY_CREATE = "capability_create"
    CAPABILITY_UPDATE = "capability_update"
    CAPABILITY_DELETE = "capability_delete"
    CAPABILITY_TOGGLE = "capability_toggle"
    SKILL_CREATE = "skill_create"
    SKILL_UPDATE = "skill_update"
    SKILL_DELETE = "skill_delete"
    SKILL_TOGGLE = "skill_toggle"


class AdminLog(Base, UUIDMixin):
    """Auditable admin operation record."""

    __tablename__ = "admin_logs"
    __table_args__ = (
        Index("idx_admin_log_admin_created", "admin_id", "created_at"),
        Index("idx_admin_log_target_user_created", "target_user_id", "created_at"),
        Index("idx_admin_log_action_created", "action", "created_at"),
    )

    admin_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[AdminActionType] = mapped_column(
        SQLEnum(
            AdminActionType,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="admin_action_type",
        ),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    target_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    admin: Mapped["User"] = relationship(
        "User",
        back_populates="admin_logs",
        foreign_keys=[admin_id],
    )
    target_user: Mapped["User | None"] = relationship("User", foreign_keys=[target_user_id])

    def __repr__(self) -> str:
        return f"<AdminLog(id={self.id}, action={self.action}, admin_id={self.admin_id})>"
