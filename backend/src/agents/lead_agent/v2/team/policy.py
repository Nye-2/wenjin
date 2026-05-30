"""Team policy validation and runtime assignment helpers."""

from __future__ import annotations

from typing import Any

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
    capability_tools = list(raw_policy.get("capability_tools") or runtime.get("allowed_tools") or [])
    capability_skills = list(raw_policy.get("capability_skills") or [])

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
        workspace_tools=list(capability_tools if workspace_tools is None else workspace_tools),
        user_tools=list(capability_tools if user_tools is None else user_tools),
        capability_skills=capability_skills,
    )
    known_ids = set(templates)
    for template_id in [*policy.core_templates, *policy.optional_templates]:
        if template_id not in known_ids:
            raise TeamPolicyError(f"unknown agent template: {template_id}")
    recruitable_ids = {*policy.core_templates, *policy.optional_templates}
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
    return policy


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
        *list(affinity.get("preferred") or []),
        *list(affinity.get("can_request") or []),
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
) -> AgentInvocation:
    suffix = ""
    if template_invocation_count > 1 or template.id.endswith("code_engineer.v1"):
        suffix = f" {chr(64 + min(template_invocation_count, 26))}"
    display_name = f"{template.display_role}{suffix}"
    invocation_id = f"team.{iteration}.{template.id.replace('.', '_')}.{template_invocation_count}"
    return AgentInvocation(
        id=invocation_id,
        iteration=iteration,
        template_id=template.id,
        display_name=display_name,
        assigned_role=template.display_role,
        recruitment_reason=reason,
        input_brief=input_brief,
        effective_tools=effective_tools,
        effective_skills=effective_skills,
    )
