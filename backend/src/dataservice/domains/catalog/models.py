"""Catalog domain storage models owned by DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class CapabilityDefinition(Base, TimestampMixin):
    """Canonical mission-level capability definition."""

    __tablename__ = "capability_definitions"
    __table_args__ = (
        Index(
            "ix_capability_definitions_active",
            "workspace_type",
            "enabled",
            postgresql_where="enabled = true",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="capability.v2",
        server_default="capability.v2",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    tier: Mapped[str] = mapped_column(String(50), nullable=False, default="primary", server_default="primary")
    entry_surface: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="workbench",
        server_default="workbench",
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    intent_description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    trigger_phrases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    required_decisions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    brief_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    graph_template: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    ui_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    runtime: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    dashboard_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class CapabilitySeedRevision(Base, UUIDMixin, TimestampMixin):
    """Checksum record for idempotent catalog seed loads."""

    __tablename__ = "capability_seed_revisions"
    __table_args__ = (
        Index("ix_capability_seed_revisions_kind_root", "catalog_kind", "seed_root"),
    )

    catalog_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    seed_root: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    loaded_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
