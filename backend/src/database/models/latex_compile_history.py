"""LaTeX compile history model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDMixin

if TYPE_CHECKING:
    from .latex_project import LatexProject


class LatexCompileHistory(Base, UUIDMixin):
    """Compile record for a LaTeX project."""

    __tablename__ = "latex_compile_history"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("latex_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    main_file: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    project: Mapped["LatexProject"] = relationship(
        "LatexProject",
        back_populates="compile_history",
    )

    def __repr__(self) -> str:
        return (
            f"<LatexCompileHistory(id={self.id}, "
            f"project_id={self.project_id}, status={self.status})>"
        )
