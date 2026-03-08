"""Paper models for academic literature management."""

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .workspace import Workspace


class Paper(Base, UUIDMixin, TimestampMixin):
    """Paper model for academic literature (globally shared).

    Papers are stored once and can be referenced by multiple workspaces.
    This enables efficient storage and unified metadata management.

    Attributes:
        id: UUID primary key
        doi: Digital Object Identifier (unique, nullable)
        title: Paper title
        authors: List of authors as JSONB
        year: Publication year
        venue: Publication venue (journal, conference)
        abstract: Paper abstract
        file_path: Path to uploaded PDF file
        source: Source of paper data (semantic_scholar, manual_upload)
        external_ids: External identifiers (Semantic Scholar ID, etc.)
        toc: Table of contents as JSONB (list of section info)
        citation_count: Number of citations
        reference_count: Number of references
    """

    __tablename__ = "papers"

    doi: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual_upload",
    )
    external_ids: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    toc: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    workspace_papers: Mapped[list["WorkspacePaper"]] = relationship(
        "WorkspacePaper",
        back_populates="paper",
        cascade="all, delete-orphan",
    )
    extractions: Mapped[list["PaperExtraction"]] = relationship(
        "PaperExtraction",
        back_populates="paper",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["PaperChunk"]] = relationship(
        "PaperChunk",
        back_populates="paper",
        cascade="all, delete-orphan",
    )
    sections: Mapped[list["PaperSection"]] = relationship(
        "PaperSection",
        back_populates="paper",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Paper(id={self.id}, title={self.title[:50]}...)>"

    @property
    def first_author(self) -> str | None:
        """Get first author name."""
        if self.authors and len(self.authors) > 0:
            return self.authors[0].get("name")
        return None

    @property
    def author_names(self) -> list[str]:
        """Get list of author names."""
        return [a.get("name", "") for a in self.authors if a.get("name")]


class WorkspacePaper(Base, TimestampMixin):
    """Association table between Workspace and Paper.

    Enables many-to-many relationship with additional workspace-specific metadata.

    Attributes:
        workspace_id: Foreign key to workspace
        paper_id: Foreign key to paper
        notes: User notes for this paper in this workspace
        tags: User-defined tags
        is_primary: Whether this is a primary reference
        read_status: Reading status (unread, reading, read)
    """

    __tablename__ = "workspace_papers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "paper_id", name="uq_workspace_paper"),
        Index("ix_workspace_papers_workspace", "workspace_id"),
        Index("ix_workspace_papers_paper", "paper_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default="{}",
    )
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    read_status: Mapped[str] = mapped_column(
        String(20),
        default="unread",
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="workspace_papers")
    paper: Mapped["Paper"] = relationship("Paper", back_populates="workspace_papers")

    def __repr__(self) -> str:
        return f"<WorkspacePaper(workspace={self.workspace_id}, paper={self.paper_id})>"


class PaperExtraction(Base, UUIDMixin, TimestampMixin):
    """Paper extraction result for Two-Tier extraction pipeline.

    Tier 1: Engineering extraction (GROBID, PyMuPDF) - instant
    Tier 2: LLM extraction (Haiku, Qwen-Turbo) - seconds

    Attributes:
        paper_id: Foreign key to paper
        tier: Extraction tier (1 or 2)
        extraction_type: Type of extraction (metadata, full_text, summary)
        structured_data: Extracted data as JSONB
        processing_time_ms: Time taken for extraction
        model_used: LLM model used (for tier 2)
    """

    __tablename__ = "paper_extractions"

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    structured_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", back_populates="extractions")

    def __repr__(self) -> str:
        return f"<PaperExtraction(paper={self.paper_id}, tier={self.tier})>"


class PaperChunk(Base, UUIDMixin, TimestampMixin):
    """Paper chunk for vector storage (RAG).

    Each chunk is associated with both a paper and a workspace.
    This enables per-workspace vector search isolation while
    allowing chunks from the same paper to exist in multiple workspaces.

    Attributes:
        paper_id: Foreign key to paper
        workspace_id: Foreign key to workspace
        chunk_index: Index of this chunk within the paper
        content: Text content of the chunk
        embedding: Vector embedding (1536 dimensions for OpenAI ada-002)
        metadata: Additional metadata (page number, section, etc.)
    """

    __tablename__ = "paper_chunks"
    __table_args__ = (
        Index("ix_paper_chunks_paper_workspace", "paper_id", "workspace_id"),
        # Note: Vector index created separately via migration
    )

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(
        ARRAY(Float),
        nullable=True,
    )
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", back_populates="chunks")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="paper_chunks")

    def __repr__(self) -> str:
        return f"<PaperChunk(paper={self.paper_id}, index={self.chunk_index})>"


class PaperSection(Base, UUIDMixin, TimestampMixin):
    """Paper section model for index-based navigation.

    Stores the full text content of each section extracted from a paper.
    This enables precise section-level retrieval without using vector embeddings.

    Attributes:
        paper_id: Foreign key to paper
        workspace_id: Foreign key to workspace (for workspace isolation)
        section_title: Human-readable section title (e.g., "Model Architecture")
        section_path: Hierarchical path identifier (e.g., "3.2.1")
        page_start: Starting page number
        page_end: Ending page number
        content: Full text content of the section
        level: Nesting level (1 = top-level, 2 = subsection, etc.)
    """

    __tablename__ = "paper_sections"
    __table_args__ = (
        Index("ix_paper_sections_paper_workspace", "paper_id", "workspace_id"),
        Index("ix_paper_sections_path", "paper_id", "section_path"),
    )

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[str] = mapped_column(String(50), nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", back_populates="sections")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="paper_sections")

    def __repr__(self) -> str:
        return f"<PaperSection(paper={self.paper_id}, path={self.section_path})>"
