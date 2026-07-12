"""Mission policy and bounded worker-skill catalog models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class MissionPolicyRecord(Base):
    __tablename__ = "mission_policies"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_mission_policies_enabled_workspace", "workspace_type", "enabled"),)


class WorkerSkillRecord(Base):
    __tablename__ = "worker_skills"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    skill_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
