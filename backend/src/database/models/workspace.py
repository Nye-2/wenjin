"""Workspace model for academic project organization."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .artifact import Artifact
    from .generation import GenerationRecord
    from .paper import Paper, PaperChunk, PaperSection, WorkspacePaper
    from .user import User


class WorkspaceType(enum.StrEnum):
    """Types of academic workspaces."""
    SCI = "sci"                    # SCI Paper
    THESIS = "thesis"              # Graduate Thesis
    PROPOSAL = "proposal"          # Research Proposal
    GRANT = "grant"                # Grant Application
    LITERATURE_REVIEW = "literature_review"  # Systematic Review
    UNDERGRADUATE_THESIS = "undergraduate_thesis"  # 本科毕业设计


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
    discipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    workspace_papers: Mapped[list["WorkspacePaper"]] = relationship(
        "WorkspacePaper",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    paper_chunks: Mapped[list["PaperChunk"]] = relationship(
        "PaperChunk",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    paper_sections: Mapped[list["PaperSection"]] = relationship(
        "PaperSection",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    generation_records: Mapped[list["GenerationRecord"]] = relationship(
        "GenerationRecord",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, name={self.name}, type={self.type})>"

    @property
    def papers(self) -> list["Paper"]:
        """Get list of papers in this workspace."""
        return [wp.paper for wp in self.workspace_papers if wp.paper is not None]
