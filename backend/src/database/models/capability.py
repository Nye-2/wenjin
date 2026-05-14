"""Capability ORM model — defines available capabilities per workspace type."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Capability(Base):
    """A capability bound to a workspace_type."""

    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    intent_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_phrases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    required_decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    brief_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    graph_template: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ui_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_capabilities_active",
            "workspace_type",
            "enabled",
            postgresql_where="enabled = true",
        ),
    )

    def __repr__(self) -> str:
        return f"<Capability(id={self.id!r}, workspace_type={self.workspace_type!r})>"
