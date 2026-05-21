"""Workspace model for academic project organization."""

import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .artifact import Artifact
    from .generation import GenerationRecord
    from .thread import Thread
    from .user import User
    from .workspace_settings import WorkspaceSettings


class WorkspaceType(enum.StrEnum):
    """Types of academic workspaces."""
    SCI = "sci"                    # SCI Paper
    THESIS = "thesis"              # Graduate Thesis
    PROPOSAL = "proposal"          # Research Proposal
    SOFTWARE_COPYRIGHT = "software_copyright"  # Software Copyright
    PATENT = "patent"              # Patent Application


class Workspace(Base, UUIDMixin, TimestampMixin):
    """Workspace model for academic project organization.

    A workspace is an isolated environment for a specific academic project.
    Each workspace has its own reference library, artifacts, and generation records.

    Attributes:
        id: UUID primary key
        user_id: Owner's user ID
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, software_copyright, patent)
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
        SQLEnum(
            WorkspaceType,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            native_enum=False,
        ),
        nullable=False,
    )
    discipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    thread_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    # 1:1 link to the active session's thread.  No back_populates: the existing
    # Thread.workspace (backed by threads.workspace_id) already maps to
    # Workspace.threads (1:N).  Adding a second back_populates here would
    # conflict with that chain, so the 1:1 intentionally omits back-navigation.
    active_thread: Mapped["Thread | None"] = relationship(
        "Thread",
        foreign_keys=[thread_id],
        lazy="selectin",
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
    threads: Mapped[list["Thread"]] = relationship(
        "Thread",
        back_populates="workspace",
        foreign_keys="Thread.workspace_id",
        passive_deletes=True,
    )
    settings: Mapped["WorkspaceSettings | None"] = relationship(
        "WorkspaceSettings",
        back_populates="workspace",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, name={self.name}, type={self.type})>"
