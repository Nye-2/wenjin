"""Pydantic schema models for capability / capability_skill YAMLs.

These models drive admin save-time validation. Cross-reference checks (skill_id
existence, subagent_type in registry) live in the service layer because they
require DB / registry lookups; this module is pure data validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    runtime: RuntimeProfileModel = Field(default_factory=RuntimeProfileModel)
    dashboard_meta: DashboardMetaModel = Field(default_factory=DashboardMetaModel)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Capability v2 YAML schema models
# ---------------------------------------------------------------------------


class CapabilityV2DisplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    icon: str
    color: str
    order: int = 0
    entry_tier: Literal["primary", "contextual", "utility", "hidden"] = "primary"


class CapabilityV2IntentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    trigger_phrases: list[str] = Field(default_factory=list)
    disambiguation: dict[str, Any] = Field(default_factory=dict)


class CapabilityV2MissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str
    primary_surface: Literal["prism", "rooms", "sandbox", "none"]
    document_role: str | None = None
    user_promise: str
    allowed_deliverables: list[str] = Field(default_factory=list)


class CapabilityV2RequiredDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    ask: str
    type: Literal["string", "number", "boolean"]
    persist_as: Literal["decision", "memory", "none"] = "decision"


class CapabilityV2InputsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_decisions: list[CapabilityV2RequiredDecisionModel] = Field(default_factory=list)
    brief_schema: dict[str, Any]


class CapabilityV2ContextPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_reads: dict[str, Any] = Field(default_factory=dict)
    prism_context: dict[str, Any] = Field(default_factory=dict)
    full_text_access: Literal["none", "summary", "explicit_tool_only", "allowed"] = "explicit_tool_only"


class CapabilityV2SandboxIsolationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["docker"] = "docker"
    network: Literal["none", "default_deny_allowlist", "restricted_egress"] = "default_deny_allowlist"
    allow_host_docker_socket: bool = False
    allow_docker_socket: bool = False
    allow_privileged: bool = False
    allow_host_network: bool = False
    allow_host_paths: bool = False
    allow_sibling_containers: bool = False
    allow_sibling_container_access: bool = False
    allow_server_control: bool = False

    @model_validator(mode="after")
    def reject_forbidden_controls(self) -> "CapabilityV2SandboxIsolationModel":
        forbidden = {
            "allow_host_docker_socket": self.allow_host_docker_socket,
            "allow_docker_socket": self.allow_docker_socket,
            "allow_privileged": self.allow_privileged,
            "allow_host_network": self.allow_host_network,
            "allow_host_paths": self.allow_host_paths,
            "allow_sibling_containers": self.allow_sibling_containers,
            "allow_sibling_container_access": self.allow_sibling_container_access,
            "allow_server_control": self.allow_server_control,
        }
        enabled = sorted(key for key, value in forbidden.items() if value)
        if enabled:
            raise ValueError(
                "sandbox isolation enables forbidden host/container controls: "
                + ", ".join(enabled)
            )
        return self


class CapabilityV2SandboxPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["none", "optional", "conditional", "required"] = "none"
    profiles: list[str] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=list)
    isolation: CapabilityV2SandboxIsolationModel = Field(default_factory=CapabilityV2SandboxIsolationModel)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)


class CapabilityV2ReviewPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_targets: list[str] = Field(default_factory=list)
    require_user_acceptance: bool = True
    allow_bulk_accept: bool = True


class CapabilityV2YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["capability.v2"]
    id: str
    workspace_type: str
    enabled: bool = True
    display: CapabilityV2DisplayModel
    intent: CapabilityV2IntentModel
    mission: CapabilityV2MissionModel
    inputs: CapabilityV2InputsModel
    context_policy: CapabilityV2ContextPolicyModel
    sandbox_policy: CapabilityV2SandboxPolicyModel
    review_policy: CapabilityV2ReviewPolicyModel
    quality_gates: list[str] = Field(default_factory=list)
    graph_template: GraphTemplateModel
    extensions: dict[str, Any] = Field(default_factory=dict)

    def to_catalog_data(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        display = data["display"]
        intent = data["intent"]
        inputs = data["inputs"]
        return {
            **data,
            "display_name": display["name"],
            "description": display.get("description") or "",
            "intent_description": intent["description"],
            "trigger_phrases": list(intent.get("trigger_phrases") or []),
            "required_decisions": list(inputs.get("required_decisions") or []),
            "brief_schema": dict(inputs.get("brief_schema") or {}),
            "ui_meta": {
                "icon": display["icon"],
                "color": display["color"],
                "order": display.get("order", 0),
                "entry_tier": display.get("entry_tier", "primary"),
                "stages": [],
            },
            "runtime": {
                "mode": "compute_agentic",
                "sandbox_policy": data["sandbox_policy"],
            },
            "dashboard_meta": {},
        }


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


class CapabilitySkillV2WorkerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    subagent_type: str
    role_prompt: str


class CapabilitySkillV2IOContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class CapabilitySkillV2ContextAccessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_reads: dict[str, Any] = Field(default_factory=dict)
    prism_context: Literal["none", "summary", "lightweight", "full"] = "summary"


class CapabilitySkillV2ToolPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_tools: list[str] = Field(default_factory=list)


class CapabilitySkillV2SandboxAccessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["none", "optional", "conditional", "required"] = "none"
    profiles: list[str] = Field(default_factory=list)


class CapabilitySkillV2YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["capability_skill.v2"]
    id: str
    enabled: bool = True
    display_name: str
    description: str = ""
    worker: CapabilitySkillV2WorkerModel
    io_contract: CapabilitySkillV2IOContractModel
    context_access: CapabilitySkillV2ContextAccessModel
    tool_policy: CapabilitySkillV2ToolPolicyModel
    sandbox_access: CapabilitySkillV2SandboxAccessModel
    quality_gates: list[str] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @property
    def subagent_type(self) -> str:
        return self.worker.subagent_type

    def to_catalog_data(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        return {
            **data,
            "worker_type": data["worker"]["category"],
            "subagent_type": data["worker"]["subagent_type"],
            "prompt": data["worker"]["role_prompt"],
            "allowed_tools": list(data["tool_policy"].get("allowed_tools") or []),
            "resources": [],
            "config": {
                "io_contract": data["io_contract"],
                "context_access": data["context_access"],
                "sandbox_access": data["sandbox_access"],
                "quality_gates": data["quality_gates"],
            },
        }


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

    async def validate_capability(
        self,
        cap: CapabilityYamlModel | CapabilityV2YamlModel,
    ) -> list[str]:
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

    async def validate_skill(
        self,
        skill: CapabilitySkillYamlModel | CapabilitySkillV2YamlModel,
    ) -> list[str]:
        errors: list[str] = []
        registry_types = self._registry_subagent_types()
        if skill.subagent_type not in registry_types:
            errors.append(f"subagent_type '{skill.subagent_type}' not in v2 subagent registry")
        return errors

    @staticmethod
    async def _existing_skill_ids(db, ids: set[str]) -> set[str]:
        from src.dataservice_client.provider import dataservice_client

        async with dataservice_client() as client:
            skills = await client.list_catalog_skills()
            return {skill.id for skill in skills if skill.id in ids}

    @staticmethod
    def _registry_subagent_types() -> set[str]:
        from src.subagents.v2.registry import REGISTRY

        return set(REGISTRY.all_names())
