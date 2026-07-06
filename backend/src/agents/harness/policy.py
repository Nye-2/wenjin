"""Effective policy resolution for the Wenjin-native agent harness."""

from __future__ import annotations

from typing import Any

from src.sandbox.workspace_layout import WORKSPACE_PROTECTED_PATHS

from .contracts import HarnessPolicy, HarnessRunContext
from .tool_names import expand_tool_names

READ_ONLY_TOOLS = frozenset(
    {
        "sandbox.list_dir",
        "sandbox.glob",
        "sandbox.grep",
        "sandbox.read_file",
        "sandbox.read_output_ref",
    }
)

TOOL_REQUIRED_PERMISSIONS: dict[str, frozenset[str]] = {
    "sandbox.list_dir": frozenset({"filesystem.read"}),
    "sandbox.glob": frozenset({"filesystem.read"}),
    "sandbox.grep": frozenset({"filesystem.read"}),
    "sandbox.read_file": frozenset({"filesystem.read"}),
    "sandbox.read_output_ref": frozenset({"filesystem.read"}),
    "sandbox.write_file": frozenset({"filesystem.write", "filesystem.diff"}),
    "sandbox.str_replace": frozenset({"filesystem.write", "filesystem.diff"}),
    "sandbox.apply_patch": frozenset({"filesystem.write", "filesystem.diff"}),
    "sandbox.register_dataset": frozenset({"filesystem.write", "filesystem.diff"}),
    "sandbox.register_artifact": frozenset({"filesystem.write", "filesystem.diff"}),
    "sandbox.run_python": frozenset({"sandbox.run_python"}),
    "sandbox.generate_figure": frozenset({"sandbox.generate_figure"}),
}

PROTECTED_PATHS = WORKSPACE_PROTECTED_PATHS


def resolve_harness_policy(ctx: HarnessRunContext) -> HarnessPolicy:
    """Resolve effective harness policy for one subagent invocation.

    Capability policy is the maximum envelope. Agent template, requested tools,
    and skill config may only narrow that envelope.
    """

    capability_tools = _capability_tools(ctx.capability_policy)
    requested_tools = _requested_tools(ctx)
    skill_tools = _skill_allowed_tools(ctx.skill)

    allowed_tools = _ordered_intersection(
        capability_tools or requested_tools or tuple(sorted(READ_ONLY_TOOLS)),
        requested_tools or capability_tools or tuple(sorted(READ_ONLY_TOOLS)),
        skill_tools if skill_tools is not None else tuple(sorted(READ_ONLY_TOOLS)),
    )

    capability_permissions = _string_set(
        ctx.capability_policy.get("permissions")
        or ctx.capability_policy.get("allowed_permissions")
        or _sandbox_policy(ctx.capability_policy).get("permissions")
    )
    if not capability_permissions:
        capability_permissions = _permissions_for_tools(capability_tools or allowed_tools)
    if "render_figures" not in _sandbox_allowed_operations(ctx.capability_policy):
        capability_permissions.discard("sandbox.generate_figure")

    filtered_tools: list[str] = []
    effective_permissions: set[str] = set()
    for tool in allowed_tools:
        required = TOOL_REQUIRED_PERMISSIONS.get(tool, frozenset())
        if required and not required.issubset(capability_permissions):
            continue
        filtered_tools.append(tool)
        effective_permissions.update(required)

    denied = set(capability_tools).union(requested_tools).union(skill_tools or ())
    denied.difference_update(filtered_tools)

    sandbox_policy = _sandbox_policy(ctx.capability_policy)
    max_total_tool_calls = int(
        sandbox_policy.get("max_total_tool_calls")
        or sandbox_policy.get("max_tool_calls")
        or 30
    )
    return HarnessPolicy(
        allowed_tools=tuple(filtered_tools),
        denied_tools=frozenset(denied),
        permissions=frozenset(effective_permissions),
        protected_paths=PROTECTED_PATHS,
        network_profile=str(sandbox_policy.get("network_profile") or "none"),
        allow_package_install=bool(
            sandbox_policy.get("allow_package_install")
            or "sandbox.install_python_packages" in effective_permissions
        ),
        max_total_tool_calls=max_total_tool_calls,
        max_repeated_identical_tool_calls=int(
            sandbox_policy.get("max_repeated_identical_tool_calls") or 5
        ),
        max_tool_calls=max_total_tool_calls,
        max_iterations=int(sandbox_policy.get("max_iterations") or 8),
        max_sandbox_seconds=int(sandbox_policy.get("timeout_seconds") or 120),
        output_budget=dict(sandbox_policy.get("output_budget") or {}),
    )


def _capability_tools(policy: dict[str, Any]) -> tuple[str, ...]:
    raw = (
        policy.get("allowed_tools")
        or policy.get("capability_tools")
        or policy.get("tools")
        or _tool_policy(policy).get("allowed_tools")
        or _runtime_policy(policy).get("allowed_tools")
    )
    explicit = _string_tuple(raw)
    if explicit:
        return explicit
    return _tools_for_sandbox_policy(_sandbox_policy(policy))


def _requested_tools(ctx: HarnessRunContext) -> tuple[str, ...]:
    explicit = _string_tuple(ctx.requested_tools)
    if explicit:
        return explicit
    affinity = ctx.agent_template.get("tool_affinity")
    if not isinstance(affinity, dict):
        return ()
    return _string_tuple(
        [
            *list(affinity.get("preferred") or []),
            *list(affinity.get("can_request") or []),
        ]
    )


def _skill_allowed_tools(skill: dict[str, Any]) -> tuple[str, ...] | None:
    if not isinstance(skill, dict) or not skill:
        return None
    if "allowed_tools" in skill:
        explicit = _string_tuple(skill.get("allowed_tools"))
        if explicit:
            return explicit
        derived = _sandbox_access_tools(skill)
        if derived:
            return derived
        return explicit
    config = skill.get("config")
    if isinstance(config, dict) and "allowed_tools" in config:
        return _string_tuple(config.get("allowed_tools"))
    derived = _sandbox_access_tools(skill)
    return derived if derived else None


def _sandbox_access_tools(skill: dict[str, Any]) -> tuple[str, ...]:
    skill_json = skill.get("skill_json")
    if not isinstance(skill_json, dict):
        return ()
    sandbox_access = skill_json.get("sandbox_access")
    if not isinstance(sandbox_access, dict):
        return ()
    mode = str(sandbox_access.get("mode") or "none").strip().lower()
    if mode in {"", "none", "disabled", "false"}:
        return ()
    profiles = {str(item).strip().lower() for item in sandbox_access.get("profiles") or []}
    tools = [
        "sandbox.list_dir",
        "sandbox.glob",
        "sandbox.grep",
        "sandbox.read_file",
        "sandbox.read_output_ref",
    ]
    if profiles.intersection({"analysis", "visualization", "python", "experiment"}) or mode in {"optional", "required"}:
        tools.append("sandbox.run_python")
    if "visualization" in profiles or mode in {"optional", "required"}:
        tools.append("sandbox.generate_figure")
    return tuple(tools)


def _runtime_policy(policy: dict[str, Any]) -> dict[str, Any]:
    runtime = policy.get("runtime")
    return runtime if isinstance(runtime, dict) else {}


def _tool_policy(policy: dict[str, Any]) -> dict[str, Any]:
    tool_policy = policy.get("tool_policy")
    return tool_policy if isinstance(tool_policy, dict) else {}


def _sandbox_policy(policy: dict[str, Any]) -> dict[str, Any]:
    sandbox = policy.get("sandbox_policy")
    return sandbox if isinstance(sandbox, dict) else {}


def _sandbox_allowed_operations(policy: dict[str, Any]) -> frozenset[str]:
    return frozenset(_string_set(_sandbox_policy(policy).get("allowed_operations")))


def _tools_for_sandbox_policy(sandbox_policy: dict[str, Any]) -> tuple[str, ...]:
    operations = frozenset(_string_set(sandbox_policy.get("allowed_operations")))
    mode = str(sandbox_policy.get("mode") or "").strip().lower()
    tools: list[str] = []
    if mode == "required":
        tools.extend(sorted(READ_ONLY_TOOLS))
    if "run_python" in operations:
        tools.append("sandbox.run_python")
    if "render_figures" in operations:
        tools.append("sandbox.generate_figure")
    return _string_tuple(tools)


def _permissions_for_tools(tools: tuple[str, ...]) -> set[str]:
    permissions: set[str] = set()
    for tool in tools:
        permissions.update(TOOL_REQUIRED_PERMISSIONS.get(tool, frozenset()))
    return permissions


def _ordered_intersection(
    first: tuple[str, ...],
    second: tuple[str, ...],
    third: tuple[str, ...],
) -> tuple[str, ...]:
    second_set = set(second)
    third_set = set(third)
    return tuple(tool for tool in first if tool in second_set and tool in third_set)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        return ()
    return expand_tool_names(str(item).strip() for item in raw_items)


def _string_set(value: Any) -> set[str]:
    return set(_string_tuple(value))
