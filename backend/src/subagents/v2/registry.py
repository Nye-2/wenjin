"""Subagent v2 registry — maps string names to SubagentBase subclasses."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from src.agents.harness.builtins import BUILTIN_TOOL_SPECS
from src.agents.harness.tool_names import CANONICAL_TOOL_ALIASES, canonical_tool_name, expand_tool_names

if TYPE_CHECKING:
    from .base import SubagentBase


BUSINESS_TEAM_TOOLS = frozenset(
    {
        "artifact_create",
        "citation_parser",
        "document_read",
        "library_read",
        "memory_read",
        "prism_change_staged",
        "prism_read",
        "web_search",
    }
)
HARNESS_TEAM_TOOLS = frozenset(spec.name for spec in BUILTIN_TOOL_SPECS)
KNOWN_TEAM_TOOLS = BUSINESS_TEAM_TOOLS | HARNESS_TEAM_TOOLS
SANDBOX_WRITE_TOOLS = frozenset(
    {
        "sandbox.write_file",
        "sandbox.str_replace",
        "sandbox.apply_patch",
        "sandbox.register_dataset",
        "sandbox.register_artifact",
    }
)
SANDBOX_EXECUTE_TOOLS = frozenset({"sandbox.run_python"})
_PUBLIC_INTERNAL_TERMS = (
    "template id",
    "skill id",
    "tool id",
    "raw tool",
    "raw tools",
    "raw log",
    "raw logs",
    "tool log",
    "harness",
    "harness ref",
    "harness refs",
    "internal scheduling",
    "scheduler queue",
    "stdout",
    "stderr",
    "agent_template",
)
_PUBLIC_INTERNAL_ID_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\.v\d+\b")


class _Registry:
    """Simple name-to-class registry for v2 subagents."""

    def __init__(self) -> None:
        self._d: dict[str, type[SubagentBase]] = {}

    def register(self, name: str, cls: type[SubagentBase]) -> None:
        """Register a subagent class under the given name.

        Also sets cls.name = name so the class knows its own registration key.
        """
        self._d[name] = cls
        cls.name = name

    def get(self, name: str) -> type[SubagentBase]:
        """Retrieve a registered subagent class by name.

        Raises:
            KeyError: If no subagent is registered under that name.
        """
        if name not in self._d:
            raise KeyError(f"subagent '{name}' not registered")
        return self._d[name]

    def all_names(self) -> list[str]:
        """Return all registered subagent names."""
        return list(self._d.keys())


#: Global singleton registry — import this to register or look up subagents.
REGISTRY = _Registry()


def subagent(name: str):
    """Class decorator that registers a SubagentBase subclass in the global REGISTRY.

    Usage::

        @subagent("searcher")
        class Searcher(SubagentBase):
            ...
    """

    def decorator(cls):
        REGISTRY.register(name, cls)
        return cls

    return decorator


def normalize_agent_template_tool_affinity(template: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return canonical preferred/can_request tools for an agent template."""

    affinity = template.get("tool_affinity")
    if not isinstance(affinity, Mapping):
        return {"preferred": [], "can_request": []}
    return {
        "preferred": _canonical_tool_list(affinity.get("preferred")),
        "can_request": _canonical_tool_list(affinity.get("can_request")),
    }


def agent_template_requires_harness_context(template: Mapping[str, Any]) -> bool:
    """Whether the template can invoke Wenjin-native harness tools."""

    affinity = normalize_agent_template_tool_affinity(template)
    return any(
        tool.startswith("sandbox.")
        for tool in [*affinity["preferred"], *affinity["can_request"]]
    )


def validate_agent_template_contract(template: Mapping[str, Any]) -> list[str]:
    """Validate seed/admin agent template declarations against harness/team tools.

    Business tools are intentionally kept as team-level tools. Harness tools are
    required to use canonical built-in names so runtime policy can narrow them
    deterministically.
    """

    template_id = str(template.get("id") or "<unknown>").strip() or "<unknown>"
    errors: list[str] = []
    persona_prompt = str(template.get("persona_prompt") or "")
    if "Role Boundary:" not in persona_prompt:
        errors.append(f"{template_id}: persona_prompt must include Role Boundary:")
    if "Evidence Rules:" not in persona_prompt and "Safety Boundary:" not in persona_prompt:
        errors.append(
            f"{template_id}: persona_prompt must include Evidence Rules: or Safety Boundary:"
        )
    _reject_internal_terms(
        template_id=template_id,
        path="persona_prompt",
        value=persona_prompt,
        errors=errors,
    )

    expert_profile = template.get("expert_profile")
    if isinstance(expert_profile, Mapping):
        _validate_public_profile_text(
            template_id=template_id,
            profile=expert_profile,
            errors=errors,
        )

    affinity = template.get("tool_affinity")
    if not isinstance(affinity, Mapping):
        return errors

    raw_tools_by_field = {
        "preferred": _raw_string_list(affinity.get("preferred")),
        "can_request": _raw_string_list(affinity.get("can_request")),
    }
    canonical_tools: list[str] = []
    for field, raw_tools in raw_tools_by_field.items():
        for raw_tool in raw_tools:
            canonical = canonical_tool_name(raw_tool)
            if raw_tool in CANONICAL_TOOL_ALIASES:
                errors.append(
                    f"{template_id}: tool_affinity.{field} uses retired harness tool "
                    f"'{raw_tool}'; use '{canonical}'"
                )
            if canonical not in KNOWN_TEAM_TOOLS:
                errors.append(
                    f"{template_id}: tool_affinity.{field} declares unknown team tool "
                    f"'{raw_tool}'"
                )
            if canonical not in canonical_tools:
                canonical_tools.append(canonical)
        for companion in expand_tool_names(raw_tools):
            if companion not in canonical_tools:
                canonical_tools.append(companion)

    risk_profile = template.get("risk_profile")
    if not isinstance(risk_profile, Mapping):
        risk_profile = {}
    if SANDBOX_WRITE_TOOLS.intersection(canonical_tools) and risk_profile.get("filesystem") != "sandbox_only":
        errors.append(
            f"{template_id}: sandbox write tools require "
            "risk_profile.filesystem='sandbox_only'"
        )
    code_execution = str(risk_profile.get("code_execution") or "").strip()
    if SANDBOX_EXECUTE_TOOLS.intersection(canonical_tools) and code_execution not in {
        "optional",
        "required",
    }:
        errors.append(
            f"{template_id}: sandbox.run_python requires "
            "risk_profile.code_execution optional|required"
        )
    return errors


def _validate_public_profile_text(
    *,
    template_id: str,
    profile: Mapping[str, Any],
    errors: list[str],
) -> None:
    for field in ("public_name", "short_name", "role_title", "tagline"):
        _reject_internal_terms(
            template_id=template_id,
            path=f"expert_profile.{field}",
            value=profile.get(field),
            errors=errors,
        )

    status_phrases = profile.get("status_phrases")
    if not isinstance(status_phrases, Mapping):
        return
    for key, value in status_phrases.items():
        _reject_internal_terms(
            template_id=template_id,
            path=f"expert_profile.status_phrases.{key}",
            value=value,
            errors=errors,
        )


def _reject_internal_terms(
    *,
    template_id: str,
    path: str,
    value: Any,
    errors: list[str],
) -> None:
    text = str(value or "").lower()
    for term in _PUBLIC_INTERNAL_TERMS:
        if term in text:
            errors.append(
                f"{template_id}: {path} contains internal terminology '{term}'"
            )
            return
    match = _PUBLIC_INTERNAL_ID_PATTERN.search(text)
    if match:
        errors.append(
            f"{template_id}: {path} contains internal terminology '{match.group(0)}'"
        )


def _canonical_tool_list(value: Any) -> list[str]:
    result: list[str] = []
    for raw in _raw_string_list(value):
        canonical = canonical_tool_name(raw)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _raw_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
    else:
        return []
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result
