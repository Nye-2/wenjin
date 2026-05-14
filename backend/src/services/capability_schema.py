"""Pydantic schema models for capability YAMLs.

Built up incrementally:
- P6 introduces: RuntimeProfileModel, DashboardMetaModel, FeatureRuntimeMode
- P3 will add: CapabilityYamlModel, CapabilitySkillYamlModel, CrossRefValidator
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureRuntimeMode(StrEnum):
    """Execution mode for a capability. Mirrors v1 enum from workspace_features.runtime_profiles."""
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
    status_kind: str = "default"      # which DashboardService mixin to call
    panel: str | None = None          # legacy panel name (kept for compatibility)
