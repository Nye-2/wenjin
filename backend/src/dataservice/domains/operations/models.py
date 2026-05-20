"""Operational metadata tables for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class DataServiceIdempotencyKey(Base, UUIDMixin, TimestampMixin):
    """Tracks idempotent command execution at the DataService boundary."""

    __tablename__ = "dataservice_idempotency_keys"
    __table_args__ = (
        UniqueConstraint("scope_hash", "idempotency_key", name="uq_dataservice_idempotency_scope_key"),
        Index("ix_dataservice_idempotency_workspace", "workspace_id"),
        Index("ix_dataservice_idempotency_actor", "actor_user_id"),
        Index("ix_dataservice_idempotency_status", "status"),
    )

    source_service: Mapped[str] = mapped_column(String(80), nullable=False)
    command_name: Mapped[str] = mapped_column(String(120), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", server_default="running")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataServiceOutboxEvent(Base, UUIDMixin, TimestampMixin):
    """Durable event emitted from a committed DataService transaction."""

    __tablename__ = "dataservice_outbox_events"
    __table_args__ = (
        Index("ix_dataservice_outbox_status_created", "status", "created_at"),
        Index("ix_dataservice_outbox_workspace", "workspace_id"),
        Index("ix_dataservice_outbox_aggregate", "aggregate_kind", "aggregate_id"),
    )

    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    aggregate_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataServiceMigrationReport(Base, UUIDMixin, TimestampMixin):
    """Audit report for one DataService migration stage."""

    __tablename__ = "dataservice_migration_reports"
    __table_args__ = (
        UniqueConstraint("migration_key", name="uq_dataservice_migration_reports_key"),
        Index("ix_dataservice_migration_reports_status", "status"),
    )

    migration_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_module: Mapped[str] = mapped_column(String(255), nullable=False)
    target_domain: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", server_default="planned")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
