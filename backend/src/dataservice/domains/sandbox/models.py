"""Sandbox runtime metadata models owned by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class SandboxEnvironmentRecord(Base, UUIDMixin, TimestampMixin):
    """Canonical workspace sandbox environment state."""

    __tablename__ = "sandbox_environments"
    __table_args__ = (
        Index("ix_sandbox_environments_workspace_state", "workspace_id", "state"),
        Index("ix_sandbox_environments_external", "provider", "sandbox_id"),
        Index("uq_sandbox_environments_workspace_external", "workspace_id", "sandbox_id", unique=True),
        Index(
            "uq_sandbox_environments_workspace_active",
            "workspace_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
            sqlite_where=text("state = 'active'"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_policy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="restricted_egress",
        server_default="restricted_egress",
    )
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    resource_limits_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system", server_default="system")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SandboxJobRecord(Base, UUIDMixin, TimestampMixin):
    """One reproducible Python sandbox job."""

    __tablename__ = "sandbox_job_records"
    __table_args__ = (
        Index("ix_sandbox_jobs_environment_created", "sandbox_environment_id", "created_at"),
        Index("ix_sandbox_jobs_workspace_status", "workspace_id", "status"),
        Index("ix_sandbox_jobs_mission", "mission_id", "mission_item_seq"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_environment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sandbox_environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    mission_item_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operation: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="run_python",
        server_default="run_python",
    )
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="python", server_default="python")
    runtime_image: Mapped[str] = mapped_column(String(255), nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    script_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_hashes_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    network_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_limits_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout_asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspace_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    stderr_asset_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspace_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SandboxLeaseRecord(Base, UUIDMixin, TimestampMixin):
    """Cross-worker lease for serializing one workspace sandbox."""

    __tablename__ = "sandbox_leases"
    __table_args__ = (
        Index("uq_sandbox_leases_workspace", "workspace_id", unique=True),
        Index("ix_sandbox_leases_expires_at", "expires_at"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_environment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sandbox_environments.id", ondelete="CASCADE"),
        nullable=True,
    )
    holder_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    holder_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    lease_token: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SandboxArtifactRecord(Base, UUIDMixin, TimestampMixin):
    """Sandbox-produced artifact linked to a workspace asset and review item."""

    __tablename__ = "sandbox_artifacts"
    __table_args__ = (
        Index("ix_sandbox_artifacts_job", "sandbox_job_id"),
        Index("ix_sandbox_artifacts_workspace_status", "workspace_id", "materialization_status"),
        Index("uq_sandbox_artifacts_mission_commit", "mission_commit_id", unique=True),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_environment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sandbox_environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sandbox_job_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspace_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reproducibility_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    mission_commit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_commits.commit_id", ondelete="SET NULL"),
        nullable=True,
    )
    materialization_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_review",
        server_default="pending_review",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
