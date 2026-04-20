"""LaTeX project model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .latex_compile_history import LatexCompileHistory


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

    compile_history: Mapped[list[LatexCompileHistory]] = relationship(
        "LatexCompileHistory",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<LatexProject(id={self.id}, name={self.name})>"
