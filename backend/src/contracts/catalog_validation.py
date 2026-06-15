"""Shared catalog validation contracts for capability routing and skill prompts."""

from __future__ import annotations

import re
from typing import Any

PROMPT_CONTRACT_REQUIRED_HEADINGS = (
    "Role Boundary:",
    "Input Interpretation:",
    "Operating Rules:",
    "Evidence Rules:",
    "Output Contract:",
    "Quality Gate Behavior:",
    "Failure Handling:",
    "Anti-Patterns:",
)

_PROMPT_FORBIDDEN_PHRASES = (
    "hidden chain-of-thought",
    "raw chain-of-thought",
    "reveal chain-of-thought",
    "reveal hidden reasoning",
    "show internal prompt",
    "directly write canonical workspace",
    "write canonical workspace rooms",
)

_DATA_BOUNDARY_TERMS = (
    "data, not behavioral instructions",
    "data, not instructions",
    "evidence data",
)


def validate_visible_capability_routing_contract(
    *,
    capability_id: str,
    enabled: bool,
    entry_tier: str,
    routing: dict[str, Any],
) -> None:
    if not enabled or entry_tier == "hidden":
        return
    prefix = f"{capability_id}: "
    if not routing.get("when_to_use"):
        raise ValueError(f"{prefix}visible capability requires routing.when_to_use")
    if not routing.get("not_for"):
        raise ValueError(f"{prefix}visible capability requires routing.not_for")
    if len(routing.get("positive_examples") or []) < 3:
        raise ValueError(
            f"{prefix}visible capability requires at least 3 routing.positive_examples"
        )
    if len(routing.get("negative_examples") or []) < 3:
        raise ValueError(
            f"{prefix}visible capability requires at least 3 routing.negative_examples"
        )
    minimum_context = routing.get("minimum_context") or {}
    if not minimum_context:
        raise ValueError(f"{prefix}visible capability requires routing.minimum_context")
    ask_when_missing = (routing.get("clarification") or {}).get("ask_when_missing") or {}
    missing_clarifications = [
        key
        for key, value in minimum_context.items()
        if value == "required" and key not in ask_when_missing
    ]
    if missing_clarifications:
        raise ValueError(
            f"{prefix}visible capability requires routing.clarification.ask_when_missing "
            "for required minimum_context keys: "
            + ", ".join(sorted(missing_clarifications))
        )


def validate_skill_prompt_contract(
    *,
    skill_id: str,
    prompt: str,
    output_schema: dict[str, Any],
    quality_gates: list[str],
    context_access: dict[str, Any],
    sandbox_access: dict[str, Any],
) -> None:
    text = str(prompt or "")
    for heading in PROMPT_CONTRACT_REQUIRED_HEADINGS:
        count = text.count(heading)
        if count != 1:
            raise ValueError(
                f"{skill_id}: worker.role_prompt must contain heading {heading!r} exactly once"
            )
        if not section_text(text, heading):
            raise ValueError(
                f"{skill_id}: worker.role_prompt heading {heading!r} must have content"
            )

    lower = text.lower()
    for phrase in _PROMPT_FORBIDDEN_PHRASES:
        if phrase in lower:
            raise ValueError(f"{skill_id}: worker.role_prompt contains forbidden phrase {phrase!r}")

    output_section = section_text(text, "Output Contract:")
    properties = output_schema.get("properties") if isinstance(output_schema, dict) else {}
    if not isinstance(properties, dict):
        properties = {}
    property_names = {str(name) for name in properties}
    if property_names and not any(
        _contains_literal_property_name(output_section, name)
        for name in property_names
    ):
        raise ValueError(
            f"{skill_id}: Output Contract must mention at least one output_schema property"
        )

    if quality_gates:
        quality_section = section_text(text, "Quality Gate Behavior:")
        if "quality_gates_checked" not in quality_section:
            raise ValueError(
                f"{skill_id}: Quality Gate Behavior must mention quality_gates_checked"
            )

    reads_context = bool(context_access.get("room_reads")) or context_access.get("prism_context") != "none"
    uses_sandbox = sandbox_access.get("mode") != "none"
    if reads_context or uses_sandbox:
        evidence_section = section_text(text, "Evidence Rules:")
        if not any(term in evidence_section.lower() for term in _DATA_BOUNDARY_TERMS):
            raise ValueError(
                f"{skill_id}: Evidence Rules must treat external/context material as data"
            )


def section_text(prompt: str, heading: str) -> str:
    start = prompt.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_positions = [
        pos
        for other in PROMPT_CONTRACT_REQUIRED_HEADINGS
        if other != heading
        for pos in [prompt.find(other, body_start)]
        if pos >= 0
    ]
    body_end = min(next_positions) if next_positions else len(prompt)
    return prompt[body_start:body_end].strip()


def _contains_literal_property_name(text: str, property_name: str) -> bool:
    if not property_name:
        return False
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(property_name)}(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None
