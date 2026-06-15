"""Pydantic schema models for capability / capability_skill YAMLs.

These models drive admin save-time validation. Cross-reference checks (skill_id
existence, subagent_type in registry) live in the service layer because they
require DataService / registry lookups; this module is pure data validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.research_evidence import validate_research_surfaces
from src.contracts.team_presentation import CapabilityTeamPresentationV1

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
    def reject_forbidden_controls(self) -> CapabilityV2SandboxIsolationModel:
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


class CapabilityV2CitationPolicyModel(BaseModel):
    """Runtime contract for workspace-scoped citation handling."""

    model_config = ConfigDict(extra="forbid")
    source_scope: Literal["none", "workspace_library"] = "none"
    required_for_prism_manuscript: bool = False
    allowed_commands: list[
        Literal["cite", "citep", "citet", "citealp", "parencite", "textcite"]
    ] = Field(default_factory=lambda: ["cite"])
    bibliography_file: str = "refs.bib"
    bibliography_command: str = "\\bibliography{refs}"
    missing_key_behavior: Literal["warn", "block_prism_stage"] = "warn"
    record_usage: bool = True


class CapabilityV2RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["team_kernel"]
    allowed_tools: list[str] = Field(default_factory=list)


class CapabilityV2TeamPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    core_templates: list[str] = Field(default_factory=list)
    optional_templates: list[str] = Field(default_factory=list)
    capability_tools: list[str] = Field(default_factory=list)
    capability_skills: list[str] = Field(default_factory=list)
    contract_overlay_skills: list[str] = Field(default_factory=list)
    contract_overlay_categories: list[str] = Field(default_factory=list)
    recruitment_triggers: dict[str, Any] = Field(default_factory=dict)
    quality_pipeline: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)


class CapabilityV2ResearchEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_surfaces: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CapabilityV2RoutingOptionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    capability_id: str


class CapabilityV2RoutingChoiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    options: list[CapabilityV2RoutingOptionModel] = Field(default_factory=list)


class CapabilityV2RoutingAmbiguityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overlaps_with: list[str] = Field(default_factory=list)
    ask_user_when: list[str] = Field(default_factory=list)


class CapabilityV2RoutingClarificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ask_when_missing: dict[str, str] = Field(default_factory=dict)
    choice_when_ambiguous: dict[str, CapabilityV2RoutingChoiceModel] = Field(default_factory=dict)


class CapabilityV2RoutingGuidanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    launch_intro: str | None = None
    clarification_prefix: str | None = None
    lightweight_answer_hint: str | None = None


class CapabilityV2RoutingModel(BaseModel):
    """User-intent and UX guidance for Chat Agent capability routing."""

    model_config = ConfigDict(extra="forbid")
    when_to_use: list[str] = Field(default_factory=list)
    not_for: list[str] = Field(default_factory=list)
    user_intents: list[str] = Field(default_factory=list)
    positive_examples: list[str] = Field(default_factory=list)
    negative_examples: list[str] = Field(default_factory=list)
    minimum_context: dict[str, Literal["required", "optional"]] = Field(default_factory=dict)
    ambiguity: CapabilityV2RoutingAmbiguityModel = Field(
        default_factory=CapabilityV2RoutingAmbiguityModel,
    )
    clarification: CapabilityV2RoutingClarificationModel = Field(
        default_factory=CapabilityV2RoutingClarificationModel,
    )
    user_guidance: CapabilityV2RoutingGuidanceModel = Field(
        default_factory=CapabilityV2RoutingGuidanceModel,
    )


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
    citation_policy: CapabilityV2CitationPolicyModel = Field(default_factory=CapabilityV2CitationPolicyModel)
    quality_gates: list[str] = Field(default_factory=list)
    research_evidence: CapabilityV2ResearchEvidenceModel = Field(
        default_factory=CapabilityV2ResearchEvidenceModel,
    )
    routing: CapabilityV2RoutingModel = Field(default_factory=CapabilityV2RoutingModel)
    runtime: CapabilityV2RuntimeModel | None = None
    team_policy: CapabilityV2TeamPolicyModel | None = None
    graph_template: GraphTemplateModel
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, value: dict[str, Any]) -> dict[str, Any]:
        extensions = dict(value or {})
        if "team_presentation" in extensions:
            presentation = CapabilityTeamPresentationV1.model_validate(
                extensions["team_presentation"],
            )
            extensions["team_presentation"] = presentation.model_dump(
                mode="json",
                exclude_none=True,
            )
        return extensions

    @model_validator(mode="after")
    def validate_team_kernel_contract(self) -> CapabilityV2YamlModel:
        _validate_non_blank_ids(self.quality_gates, "quality_gates")
        _validate_non_blank_ids(
            self.research_evidence.required_surfaces,
            "research_evidence.required_surfaces",
        )
        validate_research_surfaces(
            self.research_evidence.required_surfaces,
            field_name="research_evidence.required_surfaces",
        )
        if self.runtime is None:
            if self.team_policy is not None:
                raise ValueError("team_policy requires runtime.mode=team_kernel")
            return self
        if self.runtime.mode == "team_kernel" and self.team_policy is None:
            raise ValueError("runtime.mode=team_kernel requires team_policy")
        if self.runtime.mode == "team_kernel" and self.team_policy is not None:
            _validate_non_blank_ids(
                self.team_policy.quality_pipeline,
                "team_policy.quality_pipeline",
            )
            if not self.team_policy.quality_pipeline:
                raise ValueError("runtime.mode=team_kernel requires team_policy.quality_pipeline")
        return self

    def to_catalog_data(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        display = data["display"]
        intent = data["intent"]
        inputs = data["inputs"]
        runtime = data.get("runtime") or {
            "mode": "compute_agentic",
            "sandbox_policy": data["sandbox_policy"],
        }
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
            "runtime": runtime,
            "dashboard_meta": {},
            "routing": dict(data.get("routing") or {}),
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

    @model_validator(mode="after")
    def validate_quality_contract_shape(self) -> CapabilitySkillV2YamlModel:
        _validate_non_blank_ids(self.quality_gates, "quality_gates")
        output_schema = self.io_contract.output_schema
        if output_schema and output_schema.get("type") != "object":
            raise ValueError("io_contract.output_schema must declare type=object")
        if self.quality_gates:
            properties = output_schema.get("properties")
            if not isinstance(properties, dict):
                properties = {}
            required = output_schema.get("required")
            if not isinstance(required, list):
                required = []
            if "quality_gates_checked" not in properties or "quality_gates_checked" not in required:
                raise ValueError(
                    "skills with quality_gates must expose quality_gates_checked in output_schema"
                )
        return self

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
                "extensions": data["extensions"],
            },
        }


# ---------------------------------------------------------------------------
# Cross-reference validator
# ---------------------------------------------------------------------------


class CrossRefValidator:
    """Validates cross-references that require DataService / registry lookups.

    Pure-data validation lives in the Pydantic models. This class adds:
    - skill_id references resolve to an existing capability_skill row
    - subagent_type values exist in the v2 subagent registry
    """

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
            existing = await self._existing_skill_ids(skill_ids)
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
    async def _existing_skill_ids(ids: set[str]) -> set[str]:
        from src.dataservice_client.provider import dataservice_client

        async with dataservice_client() as client:
            skills = await client.list_catalog_skills()
            return {skill.id for skill in skills if skill.id in ids}

    @staticmethod
    def _registry_subagent_types() -> set[str]:
        from src.subagents.v2.registry import REGISTRY

        return set(REGISTRY.all_names())


def _validate_non_blank_ids(values: list[str], field_name: str) -> None:
    for value in values:
        if not str(value).strip():
            raise ValueError(f"{field_name} entries must be non-empty strings")
