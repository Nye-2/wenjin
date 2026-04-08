"""LaTeX template catalog model."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class LatexTemplate(Base):
    """Catalog entry for bootstrapping a LaTeX project."""

    __tablename__ = "latex_templates"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    main_file: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="main.tex",
        server_default="main.tex",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="academic",
        server_default="academic",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    template_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<LatexTemplate(id={self.id}, label={self.label})>"
