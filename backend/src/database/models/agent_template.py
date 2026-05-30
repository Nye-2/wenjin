"""AgentTemplate ORM model - DataService-owned recruitable expert archetypes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AgentTemplate(Base, TimestampMixin):
    """Recruitable expert archetype used by the Lead Agent team kernel."""

    __tablename__ = "agent_templates"
    __table_args__ = (
        Index(
            "ix_agent_templates_enabled_category",
            "enabled",
            "category",
            postgresql_where="enabled = true",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="agent_template.v1",
        server_default="agent_template.v1",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_role: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    persona_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    tool_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    risk_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    output_contracts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    quality_expectations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    runtime_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    template_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentTemplate(id={self.id!r}, display_role={self.display_role!r})>"
