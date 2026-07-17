"""LaTeX project model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class LatexProject(Base, UUIDMixin, TimestampMixin):
    """Metadata for a user-owned LaTeX project."""

    __tablename__ = "latex_projects"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    main_file: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="main.tex",
        server_default="main.tex",
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    trashed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    trashed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    file_order: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    llm_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    surface_role: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<LatexProject(id={self.id}, name={self.name})>"


Index(
    "uq_latex_projects_workspace_primary_manuscript",
    LatexProject.workspace_id,
    unique=True,
    postgresql_where=LatexProject.surface_role == "primary_manuscript",
    sqlite_where=LatexProject.surface_role == "primary_manuscript",
)
