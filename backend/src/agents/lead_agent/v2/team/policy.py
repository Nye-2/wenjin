"""Team policy validation and runtime assignment helpers."""

from __future__ import annotations

from typing import Any

from src.agents.harness.tool_names import expand_tool_names
from src.agents.lead_agent.v2.capability_preflight import validate_capability_tool_names
from src.contracts.team_presentation import CapabilityTeamPresentationV1, resolve_expert_profile

from .contracts import AgentInvocation, AgentTemplate, CapabilityTeamPolicy

DIRECT_COMMIT_TOOLS = {"room_commit", "workspace_room_write", "prism_apply"}
PLATFORM_MAX = {
    "max_iterations": 8,
    "max_parallel_invocations": 5,
    "max_invocations_total": 24,
    "max_invocations_per_template": 6,
    "no_progress_rounds_before_stop": 4,
}


class TeamPolicyError(ValueError):
    """Raised when a capability team policy is invalid."""


def build_capability_team_policy(
    capability: Any,
    *,
    templates: dict[str, AgentTemplate],
    workspace_tools: list[str] | None = None,
    user_tools: list[str] | None = None,
) -> CapabilityTeamPolicy:
    definition = getattr(capability, "definition_json", None)
    if not isinstance(definition, dict):
        definition = {}
    raw_policy = definition.get("team_policy")
    if not isinstance(raw_policy, dict):
        raise TeamPolicyError("team_kernel capability requires definition_json.team_policy")

    raw_limits = dict(raw_policy.get("limits") or {})
    for key, platform_max in PLATFORM_MAX.items():
        if key in raw_limits:
            raw_limits[key] = min(int(raw_limits[key]), platform_max)

    raw_budget = dict(raw_policy.get("budget") or {})
    runtime = getattr(capability, "runtime", None)
    if not isinstance(runtime, dict):
        runtime = {}
    capability_tools = _canonicalize_tools(raw_policy.get("capability_tools") or runtime.get("allowed_tools") or [])
    capability_skills = list(raw_policy.get("capability_skills") or [])
    contract_overlay_skills = list(raw_policy.get("contract_overlay_skills") or [])
    contract_overlay_categories = list(raw_policy.get("contract_overlay_categories") or [])
    template_profile_overrides = _extract_template_profile_overrides(definition)

    policy = CapabilityTeamPolicy(
        core_templates=list(raw_policy.get("core_templates") or []),
        optional_templates=list(raw_policy.get("optional_templates") or []),
        recruitment_triggers=dict(raw_policy.get("recruitment_triggers") or {}),
        quality_pipeline=list(
            raw_policy.get("quality_pipeline")
            or definition.get("quality_pipeline")
            or definition.get("quality_gates")
            or []
        ),
        limits=raw_limits,
        budget=raw_budget,
        capability_tools=capability_tools,
        workspace_tools=list(capability_tools if workspace_tools is None else _canonicalize_tools(workspace_tools)),
        user_tools=list(capability_tools if user_tools is None else _canonicalize_tools(user_tools)),
        capability_skills=capability_skills,
        contract_overlay_skills=contract_overlay_skills,
        contract_overlay_categories=contract_overlay_categories,
        template_profile_overrides=template_profile_overrides,
    )
    known_ids = set(templates)
    for template_id in [*policy.core_templates, *policy.optional_templates]:
        if template_id not in known_ids:
            raise TeamPolicyError(f"unknown agent template: {template_id}")
    recruitable_ids = {*policy.core_templates, *policy.optional_templates}
    for template_id in policy.template_profile_overrides:
        if template_id not in known_ids:
            raise TeamPolicyError(f"unknown team_presentation template override: {template_id}")
        if template_id not in recruitable_ids:
            raise TeamPolicyError(f"team_presentation override outside team_policy: {template_id}")
    for trigger_key, raw_templates in policy.recruitment_triggers.items():
        trigger_templates = _normalize_trigger_templates(raw_templates)
        for template_id in trigger_templates:
            if template_id not in known_ids:
                raise TeamPolicyError(
                    f"unknown recruitment trigger template: {trigger_key}.{template_id}"
                )
            if template_id not in recruitable_ids:
                raise TeamPolicyError(
                    f"recruitment trigger template outside team_policy: {trigger_key}.{template_id}"
                )
    if not policy.core_templates and not policy.optional_templates:
        raise TeamPolicyError("team_policy must declare at least one template")
    for field_name, tools in (
        ("team_policy.capability_tools", policy.capability_tools),
        ("team_policy.workspace_tools", policy.workspace_tools),
        ("team_policy.user_tools", policy.user_tools),
    ):
        validate_capability_tool_names(tools, field_name=field_name)
    for template_id in recruitable_ids:
        affinity = templates[template_id].tool_affinity or {}
        validate_capability_tool_names(
            affinity.get("preferred"),
            field_name=f"agent_template.{template_id}.tool_affinity.preferred",
        )
        validate_capability_tool_names(
            affinity.get("can_request"),
            field_name=f"agent_template.{template_id}.tool_affinity.can_request",
        )
    return policy


def _extract_template_profile_overrides(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_extensions = definition.get("extensions")
    if not isinstance(raw_extensions, dict):
        return {}
    raw_presentation = raw_extensions.get("team_presentation")
    if raw_presentation is None:
        return {}
    presentation = CapabilityTeamPresentationV1.model_validate(raw_presentation)
    return {
        template_id: override.model_dump(mode="json", exclude_none=True)
        for template_id, override in presentation.template_overrides.items()
    }


def _normalize_trigger_templates(raw_templates: Any) -> list[str]:
    if raw_templates is None:
        return []
    if isinstance(raw_templates, str):
        return [raw_templates]
    if isinstance(raw_templates, list):
        return [str(template_id) for template_id in raw_templates]
    raise TeamPolicyError("recruitment_triggers values must be template id strings or lists")


def resolve_effective_tools(template: AgentTemplate, policy: CapabilityTeamPolicy) -> list[str]:
    affinity = template.tool_affinity or {}
    requested = [
        *_canonicalize_tools(affinity.get("preferred") or []),
        *_canonicalize_tools(affinity.get("can_request") or []),
    ]
    allowed = set(policy.capability_tools or requested)
    allowed &= set(policy.workspace_tools)
    allowed &= set(policy.user_tools)
    result: list[str] = []
    for tool in requested:
        if tool in DIRECT_COMMIT_TOOLS:
            continue
        if tool in allowed and tool not in result:
            result.append(tool)
    return result


def _canonicalize_tools(raw_tools: Any) -> list[str]:
    if raw_tools is None:
        return []
    if isinstance(raw_tools, str):
        items = [raw_tools]
    elif isinstance(raw_tools, (list, tuple, set, frozenset)):
        items = list(raw_tools)
    else:
        return []
    return list(expand_tool_names(str(item).strip() for item in items))


def resolve_effective_skills(
    template: AgentTemplate,
    *,
    requested_skills: list[str] | None = None,
    capability_skills: list[str] | None = None,
) -> list[str]:
    requested = [*template.default_skills, *list(requested_skills or [])]
    allowed = set(capability_skills or requested)
    result: list[str] = []
    for skill_id in requested:
        if skill_id in allowed and skill_id not in result:
            result.append(skill_id)
    return result


def build_invocation_assignment(
    *,
    template: AgentTemplate,
    iteration: int,
    template_invocation_count: int,
    reason: str,
    input_brief: dict[str, Any],
    effective_tools: list[str],
    effective_skills: list[str],
    profile_override: dict[str, Any] | None = None,
) -> AgentInvocation:
    suffix = ""
    if template_invocation_count > 1 or template.id.endswith("code_engineer.v1"):
        suffix = f" {chr(64 + min(template_invocation_count, 26))}"
    expert_profile = resolve_expert_profile(
        base_profile=template.expert_profile or None,
        display_role=template.display_role,
        override=profile_override,
    )
    display_name = f"{expert_profile.public_name}{suffix}"
    invocation_id = f"team.{iteration}.{template.id.replace('.', '_')}.{template_invocation_count}"
    return AgentInvocation(
        id=invocation_id,
        iteration=iteration,
        template_id=template.id,
        display_name=display_name,
        assigned_role=expert_profile.role_title,
        recruitment_reason=reason,
        input_brief=input_brief,
        effective_tools=effective_tools,
        effective_skills=effective_skills,
        expert_profile=expert_profile.model_dump(mode="json", exclude_none=True),
    )
