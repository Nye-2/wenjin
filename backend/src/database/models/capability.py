"""Capability models — data-driven capability definitions."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class Capability(Base):
    """A capability definition (data-driven, not code).

    Composite primary key: (id, workspace_type, version).

    Attributes:
        id: Capability identifier (e.g. deep_research)
        workspace_type: Workspace type this capability belongs to
        version: Version number
        display_name: Human-readable name
        enabled: Whether this capability is active
        intent_description: Description of user intent this capability handles
        trigger_phrases: JSONB array of trigger phrases
        required_decisions: JSONB array of required decision specs
        brief_schema: JSON Schema for the capability brief
        graph_template: PhasedPlan graph template
        system_prompt: System prompt (may contain template variables)
        result_card_template: Result card template identifier
        notes: Optional notes
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
    intent_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_phrases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    required_decisions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    brief_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    graph_template: Mapped[dict] = mapped_column(JSONB, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    result_card_template: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    active_version: Mapped["CapabilityActiveVersion | None"] = relationship(
        "CapabilityActiveVersion",
        back_populates="capability",
        foreign_keys="[CapabilityActiveVersion.id, CapabilityActiveVersion.workspace_type, CapabilityActiveVersion.active_version]",
        primaryjoin="and_(Capability.id == CapabilityActiveVersion.id, "
                    "Capability.workspace_type == CapabilityActiveVersion.workspace_type, "
                    "Capability.version == CapabilityActiveVersion.active_version)",
        viewonly=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Capability(id={self.id!r}, workspace_type={self.workspace_type!r}, "
            f"version={self.version})>"
        )


class CapabilityActiveVersion(Base):
    """Tracks the active version of a capability.

    Composite primary key: (id, workspace_type).
    Foreign key references capabilities(id, workspace_type, version).

    Attributes:
        id: Capability identifier
        workspace_type: Workspace type
        active_version: The currently active version number
    """

    __tablename__ = "capability_active_versions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    active_version: Mapped[int] = mapped_column(Integer, nullable=False)

    capability: Mapped["Capability"] = relationship(
        "Capability",
        back_populates="active_version",
        foreign_keys="[CapabilityActiveVersion.id, CapabilityActiveVersion.workspace_type, CapabilityActiveVersion.active_version]",
        primaryjoin="and_(CapabilityActiveVersion.id == Capability.id, "
                    "CapabilityActiveVersion.workspace_type == Capability.workspace_type, "
                    "CapabilityActiveVersion.active_version == Capability.version)",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CapabilityActiveVersion(id={self.id!r}, workspace_type={self.workspace_type!r}, "
            f"active_version={self.active_version})>"
        )
