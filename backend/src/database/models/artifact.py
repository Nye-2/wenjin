"""Artifact model for academic outputs."""

from enum import StrEnum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .workspace import Workspace


class ArtifactType(StrEnum):
    """Types of academic artifacts."""
    RESEARCH_IDEA = "research_idea"
    METHODOLOGY = "methodology"
    FRAMEWORK_OUTLINE = "framework_outline"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    LITERATURE_REVIEW = "literature_review"
    METHODOLOGY_SECTION = "methodology_section"
    EXPERIMENT_SECTION = "experiment_section"
    RESULTS_SECTION = "results_section"
    DISCUSSION_SECTION = "discussion_section"
    CONCLUSION = "conclusion"
    PAPER_DRAFT = "paper_draft"
    PROPOSAL = "proposal"
    REVIEW = "review"


class Artifact(Base, UUIDMixin, TimestampMixin):
    """Artifact model for academic outputs.

    Artifacts are the outputs produced by skills during the academic writing process.
    They form a directed acyclic graph (DAG) through parent_artifact_id relationships.

    Attributes:
        id: UUID primary key
        workspace_id: Foreign key to workspace
        type: Artifact type (research_idea, methodology, etc.)
        title: Optional title for the artifact
        content: Artifact content as JSONB
        created_by_skill: Name of skill that created this artifact
        parent_artifact_id: Optional parent artifact (for derived artifacts)
        version: Version number for this artifact type
        status: Status (draft, review, final)
    """

    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_workspace_type", "workspace_id", "type"),
        Index("ix_artifacts_parent", "parent_artifact_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_by_skill: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parent_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="artifacts")
    parent: Mapped[Optional["Artifact"]] = relationship(
        "Artifact",
        remote_side="Artifact.id",
        backref="children",
    )

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, type={self.type}, workspace={self.workspace_id})>"

    def get_lineage(self) -> List["Artifact"]:
        """Get artifact lineage from root to this artifact."""
        lineage = []
        current = self
        while current:
            lineage.append(current)
            current = current.parent
        return list(reversed(lineage))
