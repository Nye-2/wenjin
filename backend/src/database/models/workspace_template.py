"""Workspace template model for thesis/paper formatting templates."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class WorkspaceTemplate(Base, UUIDMixin, TimestampMixin):
    """Template defining structure and format specs for a workspace.

    Attributes:
        id: UUID primary key
        workspace_id: Owning workspace
        name: Human-readable template name
        category: Template category (e.g. thesis, sci, proposal)
        source_type: How the template was created (upload, builtin, parsed)
        source_file_path: Path to the original uploaded file, if any
        structure: JSON describing chapter/section hierarchy
        format_spec: JSON describing page layout, fonts, spacing, etc.
        content_guidelines: JSON with abstract limits, keyword counts, etc.
        latex_preamble: Optional LaTeX preamble text
        is_active: Whether this is the currently active template for its workspace
        is_builtin: Whether this is a system-provided template
    """

    __tablename__ = "workspace_templates"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    format_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_guidelines: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latex_preamble: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workspace = relationship("Workspace", backref="templates")

    def __repr__(self) -> str:
        return f"<WorkspaceTemplate(id={self.id}, name={self.name}, active={self.is_active})>"
