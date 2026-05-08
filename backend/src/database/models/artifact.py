"""Artifact model for academic outputs."""
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.artifacts import ArtifactType

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .workspace import Workspace


__all__ = ["Artifact", "ArtifactType"]


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
        UniqueConstraint(
            "workspace_id",
            "type",
            "title",
            "version",
            name="uq_artifacts_workspace_type_title_version",
        ),
        Index("ix_artifacts_workspace_type", "workspace_id", "type"),
        Index("ix_artifacts_parent", "parent_artifact_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_by_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_artifact_id: Mapped[str | None] = mapped_column(
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

    def get_lineage(self) -> list["Artifact"]:
        """Get artifact lineage from root to this artifact."""
        lineage: list[Artifact] = []
        current: Artifact | None = self
        while current is not None:
            lineage.append(current)
            current = current.parent
        return list(reversed(lineage))
