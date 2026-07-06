"""Launch-time capability configuration preflight checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.agents.harness.research_eval_surfaces import (
    validate_research_surface_enforcement,
    validate_research_surfaces,
)
from src.agents.harness.tool_names import expand_tool_names
from src.subagents.v2.registry import KNOWN_TEAM_TOOLS


class CapabilityPreflightError(ValueError):
    """Raised when a capability cannot be launched because its config is invalid."""


def validate_research_evidence_policy(capability_policy: Mapping[str, Any] | None) -> None:
    """Validate research evidence policy without applying runtime defaults."""

    policy = capability_policy if isinstance(capability_policy, Mapping) else {}
    research_evidence = policy.get("research_evidence")
    if not isinstance(research_evidence, Mapping):
        return
    try:
        validate_research_surfaces(research_evidence.get("required_surfaces"))
        validate_research_surface_enforcement(research_evidence.get("surface_enforcement"))
    except ValueError as exc:
        raise CapabilityPreflightError(str(exc)) from exc


def validate_capability_tool_names(raw_tools: Any, *, field_name: str) -> None:
    """Ensure declared capability tools map to callable team/harness tools."""

    for tool_name in _canonical_tool_list(raw_tools):
        if tool_name not in KNOWN_TEAM_TOOLS:
            raise CapabilityPreflightError(f"unknown capability tool: {tool_name}")


def validate_static_graph_preflight(
    *,
    capability: Any,
    capability_policy: Mapping[str, Any] | None,
    skills: Mapping[str, Any],
) -> None:
    """Validate static graph tasks before compiling or dispatching subagents."""

    validate_research_evidence_policy(capability_policy)
    definition = getattr(capability, "definition_json", None)
    definition = definition if isinstance(definition, Mapping) else {}
    runtime = getattr(capability, "runtime", None)
    runtime = runtime if isinstance(runtime, Mapping) else {}
    tool_policy = definition.get("tool_policy")
    tool_policy = tool_policy if isinstance(tool_policy, Mapping) else {}

    for field_name, value in (
        ("definition_json.allowed_tools", definition.get("allowed_tools")),
        ("definition_json.capability_tools", definition.get("capability_tools")),
        ("definition_json.required_tools", definition.get("required_tools")),
        ("definition_json.tool_policy.allowed_tools", tool_policy.get("allowed_tools")),
        ("runtime.allowed_tools", runtime.get("allowed_tools")),
        ("runtime.capability_tools", runtime.get("capability_tools")),
        ("runtime.required_tools", runtime.get("required_tools")),
    ):
        validate_capability_tool_names(value, field_name=field_name)

    known_skill_ids = {str(skill_id) for skill_id in skills}
    for phase_name, task in _iter_graph_tasks(getattr(capability, "graph_template", None)):
        task_name = str(task.get("name") or "<unnamed>")
        task_path = f"{phase_name}.{task_name}"
        skill_id = _clean_text(task.get("skill_id"))
        if skill_id:
            if skill_id not in known_skill_ids:
                raise CapabilityPreflightError(f"unknown capability skill: {skill_id}")
        elif task.get("allow_skillless") is not True:
            raise CapabilityPreflightError(
                f"graph task {task_path} must declare skill_id or allow_skillless=true"
            )
        validate_capability_tool_names(
            task.get("tools"),
            field_name=f"graph_template.{task_path}.tools",
        )
        validate_capability_tool_names(
            task.get("required_tools"),
            field_name=f"graph_template.{task_path}.required_tools",
        )


def static_graph_skill_ids(template: Mapping[str, Any] | None) -> set[str]:
    """Return declared skill ids from a static graph template."""

    return {
        skill_id
        for _, task in _iter_graph_tasks(template)
        for skill_id in [_clean_text(task.get("skill_id"))]
        if skill_id
    }


def _iter_graph_tasks(template: Any) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if not isinstance(template, Mapping):
        return
    for phase in template.get("phases") or []:
        if not isinstance(phase, Mapping):
            continue
        phase_name = str(phase.get("name") or "<unnamed>")
        for task in phase.get("tasks") or []:
            if isinstance(task, Mapping):
                yield phase_name, task


def _canonical_tool_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        return ()
    return expand_tool_names(str(item).strip() for item in raw_items)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
