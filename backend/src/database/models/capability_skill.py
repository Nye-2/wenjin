"""CapabilitySkill ORM model — reusable subagent capability packs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CapabilitySkill(Base):
    """A reusable capability pack a subagent can load at runtime."""

    __tablename__ = "capability_skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="capability_skill.v2",
        server_default="capability_skill.v2",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    worker_type: Mapped[str] = mapped_column(String(50), nullable=False, default="react", server_default="react")
    subagent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    resources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    skill_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CapabilitySkill(id={self.id!r}, subagent_type={self.subagent_type!r})>"
