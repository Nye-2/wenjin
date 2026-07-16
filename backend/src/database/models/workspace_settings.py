"""Workspace settings model for per-workspace configuration."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class WorkspaceSettings(Base, TimestampMixin):
    """Per-workspace configuration row (1:1 with workspaces).

    Attributes:
        workspace_id: FK to workspaces.id (PK, cascade delete)
        default_model: Optional model override for this workspace
        reasoning_effort: Default reasoning effort for new chat turns
        auto_compact_threshold: Context usage ratio that triggers auto-compaction
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
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, default="xhigh", server_default="xhigh",
    )
    auto_compact_threshold: Mapped[float] = mapped_column(
        nullable=False, default=0.8, server_default="0.8",
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="'{}'::jsonb",
    )

    __table_args__ = (
        CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high', 'xhigh')",
            name="ck_workspace_settings_reasoning_effort",
        ),
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
