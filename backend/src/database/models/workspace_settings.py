"""Workspace settings model for per-workspace configuration."""

from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class WorkspaceSettings(Base, TimestampMixin):
    """Per-workspace configuration row (1:1 with workspaces).

    Attributes:
        workspace_id: FK to workspaces.id (PK, cascade delete)
        default_model: Optional model override for this workspace
        thinking_enabled: Whether thinking mode is enabled
        sandbox_provider: Sandbox provider name (default: local)
        auto_compact_threshold: Context usage ratio that triggers auto-compaction
        capability_overrides: JSON overrides for workspace capabilities
        metadata_json: Arbitrary metadata blob
    """

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_model: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    thinking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    sandbox_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="local", server_default="local",
    )
    auto_compact_threshold: Mapped[float] = mapped_column(
        nullable=False, default=0.8, server_default="0.8",
    )
    capability_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb",
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb",
    )

    # Relationship back to workspace
    workspace: Mapped["Workspace"] = relationship(  # noqa: F821
        "Workspace",
        back_populates="settings",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkspaceSettings(workspace_id={self.workspace_id}, "
            f"model={self.default_model})>"
        )
