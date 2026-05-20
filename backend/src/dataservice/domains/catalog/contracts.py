"""Catalog domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CapabilityDefinitionRecord(BaseModel):
    """Canonical capability projection."""

    id: str
    workspace_type: str
    schema_version: str = "capability.v2"
    enabled: bool = True
    tier: str = "primary"
    entry_surface: str = "workbench"
    display_name: str
    description: str = ""
    intent_description: str = ""
    trigger_phrases: list[str] = Field(default_factory=list)
    required_decisions: list[dict[str, Any]] = Field(default_factory=list)
    brief_schema: dict[str, Any] = Field(default_factory=dict)
    graph_template: dict[str, Any] = Field(default_factory=dict)
    ui_meta: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    dashboard_meta: dict[str, Any] = Field(default_factory=dict)
    definition_json: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    checksum: str | None = None
    source_path: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CapabilitySkillRecord(BaseModel):
    """Canonical skill projection."""

    id: str
    schema_version: str = "capability_skill.v2"
    enabled: bool = True
    display_name: str
    description: str = ""
    worker_type: str
    subagent_type: str
    prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    skill_json: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    source_path: str | None = None


class SeedLoadResult(BaseModel):
    """Seed load result."""

    loaded: int
    skipped: bool = False
    checksum: str | None = None
