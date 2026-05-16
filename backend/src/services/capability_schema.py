"""Pydantic schema models for capability / capability_skill YAMLs.

These models drive admin save-time validation. Cross-reference checks (skill_id
existence, subagent_type in registry) live in the service layer because they
require DB / registry lookups; this module is pure data validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Existing models (used by other modules)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Capability YAML schema models
# ---------------------------------------------------------------------------


class UIMetaStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str


class UIMetaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    icon: str
    color: str
    order: int = 0
    stages: list[UIMetaStage] = Field(default_factory=list)
    follow_up_prompt: str | None = None


class RequiredDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    ask: str
    type: Literal["string", "number", "boolean"]


class GraphTaskOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: str
    iterate_on: str | None = None
    mapping: dict[str, Any] = Field(default_factory=dict)


class GraphTaskModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    subagent_type: str
    skill_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[GraphTaskOutputModel] = Field(default_factory=list)


class GraphPhaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    tasks: list[GraphTaskModel]


class GraphTemplateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    phases: list[GraphPhaseModel]


class CapabilityYamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    workspace_type: str
    enabled: bool = True
    display_name: str
    description: str = ""
    intent_description: str
    trigger_phrases: list[str] = Field(default_factory=list)
    required_decisions: list[RequiredDecisionModel] = Field(default_factory=list)
    brief_schema: dict[str, Any]
    graph_template: GraphTemplateModel
    ui_meta: UIMetaModel
    notes: str | None = None


# ---------------------------------------------------------------------------
# CapabilitySkill YAML schema models
# ---------------------------------------------------------------------------


class CapabilitySkillYamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    enabled: bool = True
    display_name: str
    description: str = ""
    subagent_type: str
    prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cross-reference validator
# ---------------------------------------------------------------------------


class CrossRefValidator:
    """Validates cross-references that require DB / registry lookups.

    Pure-data validation lives in the Pydantic models. This class adds:
    - skill_id references resolve to an existing capability_skill row
    - subagent_type values exist in the v2 subagent registry
    """

    def __init__(self, db) -> None:
        self.db = db

    async def validate_capability(self, cap: CapabilityYamlModel) -> list[str]:
        errors: list[str] = []

        skill_ids = {
            t.skill_id
            for phase in cap.graph_template.phases
            for t in phase.tasks
            if t.skill_id is not None
        }
        if skill_ids:
            existing = await self._existing_skill_ids(self.db, skill_ids)
            for sid in skill_ids - existing:
                errors.append(f"skill_id '{sid}' not found in capability_skills table")

        subagent_types = {
            t.subagent_type
            for phase in cap.graph_template.phases
            for t in phase.tasks
        }
        registry_types = self._registry_subagent_types()
        for st in subagent_types - registry_types:
            errors.append(f"subagent_type '{st}' not in v2 subagent registry")

        return errors

    async def validate_skill(self, skill: CapabilitySkillYamlModel) -> list[str]:
        errors: list[str] = []
        registry_types = self._registry_subagent_types()
        if skill.subagent_type not in registry_types:
            errors.append(f"subagent_type '{skill.subagent_type}' not in v2 subagent registry")
        return errors

    @staticmethod
    async def _existing_skill_ids(db, ids: set[str]) -> set[str]:
        from sqlalchemy import select
        from src.database.models.capability_skill import CapabilitySkill

        result = await db.execute(
            select(CapabilitySkill.id).where(CapabilitySkill.id.in_(ids))
        )
        return {row[0] for row in result.all()}

    @staticmethod
    def _registry_subagent_types() -> set[str]:
        from src.subagents.v2.registry import REGISTRY

        return set(REGISTRY.all_names())
