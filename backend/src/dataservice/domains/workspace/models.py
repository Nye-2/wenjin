"""Workspace domain storage models owned by DataService."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin
from src.dataservice.domains.workspace.contracts import (
    WorkspaceMembershipRole,
    WorkspaceMembershipStatus,
)


class WorkspaceMembership(Base, UUIDMixin, TimestampMixin):
    """Membership row for workspace access and ownership."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"),
        Index("ix_workspace_memberships_user_status", "user_id", "status"),
        Index("ix_workspace_memberships_workspace_role", "workspace_id", "role"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkspaceMembershipRole.OWNER.value,
        server_default=WorkspaceMembershipRole.OWNER.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkspaceMembershipStatus.ACTIVE.value,
        server_default=WorkspaceMembershipStatus.ACTIVE.value,
    )
