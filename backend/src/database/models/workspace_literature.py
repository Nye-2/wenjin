"""Workspace literature model for managing research references."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class WorkspaceLiterature(Base, UUIDMixin, TimestampMixin):
    """Workspace literature model for managing research references.

    A literature entry represents a research paper or reference within a workspace.
    This model stores bibliographic information and metadata for literature management.

    Attributes:
        id: UUID primary key
        workspace_id: Foreign key to the workspace this literature belongs to
        title: Title of the literature
        authors: List of authors (stored as JSONB)
        year: Publication year
        citations: Number of citations
        venue: Publication venue (journal, conference, etc.)
        quartile: Journal quartile (Q1, Q2, Q3, Q4)
        abstract: Abstract or summary of the literature
        doi: Digital Object Identifier
        source: Source of the literature (manual, deep_research, etc.)
        is_core: Whether this is a core reference for the thesis
    """

    __tablename__ = "workspace_literature"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quartile: Mapped[str | None] = mapped_column(String(10), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)
