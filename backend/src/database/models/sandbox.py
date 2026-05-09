"""Sandbox model for workspace sandboxes."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Sandbox(Base):
    """A sandbox environment for a workspace.

    Attributes:
        workspace_id: FK to workspaces.id (PK, cascade delete)
        sandbox_id: External sandbox identifier
        provider: Sandbox provider (local/modal)
        state: Sandbox state (active/stopped/error)
        workspace_path: Path to workspace files
        last_active_at: Last activity timestamp
        created_at: Creation timestamp
    """

    __tablename__ = "sandboxes"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sandbox_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Sandbox(workspace_id={self.workspace_id}, "
            f"provider={self.provider}, state={self.state})>"
        )
