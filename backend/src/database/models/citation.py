"""Citation model for tracking paper citation relationships."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .paper import Paper
    from .workspace import Workspace


class CitationType(enum.StrEnum):
    """Types of citations."""

    EXPLICIT = "explicit"      # Direct citation with reference
    IMPLICIT = "implicit"      # Mentioned without formal reference
    SELF = "self"              # Self-citation
    SECONDARY = "secondary"    # Cited by another source


class Citation(Base, UUIDMixin, TimestampMixin):
    """Citation relationship between papers.

    Represents a citation from one paper to another,
    with context and metadata about where the citation appears.
    """

    __tablename__ = "citations"
    __table_args__ = (
        Index("ix_citations_source", "paper_id"),
        Index("ix_citations_target", "cited_paper_id"),
        Index("ix_citations_workspace", "workspace_id"),
        UniqueConstraint("paper_id", "cited_paper_id", "workspace_id",
                        name="uq_citation_relationship"),
    )

    # Source paper (the one that cites)
    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Target paper (the one being cited)
    cited_paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Workspace context
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Citation details
    citation_type: Mapped[str] = mapped_column(
        String(20),
        default="explicit",
        nullable=False,
    )

    # Context information
    citation_context: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    section: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Relationships
    # Note: back_populates will be added in Task 3 when Paper model is updated
    paper: Mapped["Paper"] = relationship(
        "Paper",
        foreign_keys=[paper_id],
    )
    cited_paper: Mapped["Paper"] = relationship(
        "Paper",
        foreign_keys=[cited_paper_id],
    )
    workspace: Mapped["Workspace"] = relationship("Workspace")

    def __init__(self, **kwargs):
        """Initialize Citation with default citation_type."""
        if "citation_type" not in kwargs:
            kwargs["citation_type"] = CitationType.EXPLICIT
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Citation(paper={self.paper_id}, cited={self.cited_paper_id})>"
