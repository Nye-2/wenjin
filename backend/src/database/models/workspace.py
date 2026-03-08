"""Workspace model for academic project organization."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from ..base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .user import User
    from .paper import WorkspacePaper, PaperChunk, PaperSection
    from .artifact import Artifact
    from .generation import GenerationRecord


class WorkspaceType(str, enum.Enum):
    """Types of academic workspaces."""
    SCI = "sci"                    # SCI Paper
    THESIS = "thesis"              # Graduate Thesis
    PROPOSAL = "proposal"          # Research Proposal
    GRANT = "grant"                # Grant Application
    LITERATURE_REVIEW = "literature_review"  # Systematic Review


class Workspace(Base, UUIDMixin, TimestampMixin):
    """Workspace model for academic project organization.

    A workspace is an isolated environment for a specific academic project.
    Each workspace has its own set of papers, artifacts, and generation records.

    Attributes:
        id: UUID primary key
        user_id: Owner's user ID
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, grant)
        discipline: Academic discipline (e.g., computer_science)
        description: Optional description
        config: JSON configuration for workspace-specific settings
    """

    __tablename__ = "workspaces"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[WorkspaceType] = mapped_column(
        SQLEnum(WorkspaceType),
        nullable=False,
    )
    discipline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    workspace_papers: Mapped[List["WorkspacePaper"]] = relationship(
        "WorkspacePaper",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    paper_chunks: Mapped[List["PaperChunk"]] = relationship(
        "PaperChunk",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    paper_sections: Mapped[List["PaperSection"]] = relationship(
        "PaperSection",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[List["Artifact"]] = relationship(
        "Artifact",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    generation_records: Mapped[List["GenerationRecord"]] = relationship(
        "GenerationRecord",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, name={self.name}, type={self.type})>"

    @property
    def papers(self) -> List["Paper"]:
        """Get list of papers in this workspace."""
        return [wp.paper for wp in self.workspace_papers if wp.paper is not None]
