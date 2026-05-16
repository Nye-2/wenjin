"""Pydantic schema models for capability YAMLs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureRuntimeMode(StrEnum):
    """Execution mode for a capability."""
    CHAT_ONLY = "chat_only"
    DETERMINISTIC = "deterministic"
    COMPUTE_WORKFLOW = "compute_workflow"
    COMPUTE_AGENTIC = "compute_agentic"


class RuntimeProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: FeatureRuntimeMode = FeatureRuntimeMode.CHAT_ONLY
    requires_sandbox: bool = False
    review_gate: dict[str, Any] = Field(default_factory=dict)
    allowed_paths: list[str] = Field(default_factory=list)


class DashboardMetaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status_kind: str = "default"
    hidden: bool = False
    panel: str | None = None
