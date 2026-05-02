"""GenerationRecord model for skill execution tracking."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .workspace import Workspace


class GenerationRecord(Base, UUIDMixin, TimestampMixin):
    """GenerationRecord model for skill execution tracking.

    Records every skill execution for:
    - Usage analytics
    - Cost tracking
    - Reproducibility
    - Debugging

    Attributes:
        id: UUID primary key
        workspace_id: Foreign key to workspace
        thread_id: Optional LangGraph thread ID
        skill_name: Name of the skill executed
        model_name: Model used for generation
        input_summary: Summary of input (truncated)
        output_summary: Summary of output (truncated)
        duration_ms: Execution time in milliseconds
        token_usage: Token usage breakdown
        status: Execution status (success, failed, timeout)
        error_message: Error message if failed
        metadata: Additional metadata
    """

    __tablename__ = "generation_records"
    __table_args__ = (
        Index("ix_generation_records_workspace", "workspace_id"),
        Index("ix_generation_records_skill", "skill_name"),
        Index("ix_generation_records_created", "created_at"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="success",
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="generation_records",
    )

    def __repr__(self) -> str:
        return f"<GenerationRecord(id={self.id}, skill={self.skill_name})>"

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        if self.token_usage:
            return int(self.token_usage.get("total", 0))
        return 0

    @property
    def input_tokens(self) -> int:
        """Get input tokens used."""
        if self.token_usage:
            return int(self.token_usage.get("input", 0))
        return 0

    @property
    def output_tokens(self) -> int:
        """Get output tokens used."""
        if self.token_usage:
            return int(self.token_usage.get("output", 0))
        return 0
