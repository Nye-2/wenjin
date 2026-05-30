"""Runtime quality-contract resolution for Team Kernel invocations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .contracts import AgentTemplate, CapabilityTeamPolicy


class ResolvedQualityContract(BaseModel):
    """Member-level quality contract derived from existing catalog records."""

    schema_version: Literal["resolved_quality_contract.v1"] = "resolved_quality_contract.v1"
    capability_id: str
    template_id: str
    skill_ids: list[str] = Field(default_factory=list)
    role: str
    output_contracts: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    quality_gates: list[str] = Field(default_factory=list)
    acknowledgement_required_gates: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    must_rules: list[str] = Field(default_factory=list)
    should_rules: list[str] = Field(default_factory=list)
    may_rules: list[str] = Field(default_factory=list)
    recruitment_hints: dict[str, list[str]] = Field(default_factory=dict)
    source_refs: dict[str, list[str]] = Field(default_factory=dict)


class QualityContractResolver:
    """Build runtime quality contracts without creating a second catalog."""

    @classmethod
    def resolve(
        cls,
        *,
        capability: Any,
        template: AgentTemplate,
        team_policy: CapabilityTeamPolicy,
        effective_skill_ids: list[str],
        skill_records: dict[str, Any | None],
    ) -> ResolvedQualityContract:
        definition = _as_dict(getattr(capability, "definition_json", None))
        output_schema = _empty_object_schema()
        quality_gates: list[str] = []
        acknowledgement_required_gates: list[str] = []
        source_refs: dict[str, list[str]] = {}

        if team_policy.quality_pipeline:
            quality_gates.extend(team_policy.quality_pipeline)
            _add_source_ref(source_refs, "quality_gates", "team_policy.quality_pipeline")

        capability_quality_gates = _string_list(definition.get("quality_gates"))
        if capability_quality_gates:
            quality_gates.extend(capability_quality_gates)
            _add_source_ref(source_refs, "quality_gates", "capability.quality_gates")

        for skill_id in effective_skill_ids:
            skill = skill_records.get(skill_id)
            if skill is None:
                continue
            skill_data = cls._skill_contract_data(skill)
            skill_output_schema = _as_dict(
                _as_dict(skill_data.get("io_contract")).get("output_schema")
            )
            if skill_output_schema:
                output_schema = _merge_object_schemas(output_schema, skill_output_schema)
                _add_source_ref(
                    source_refs,
                    "output_schema",
                    f"skill.{skill_id}.io_contract.output_schema",
                )
            skill_quality_gates = _string_list(skill_data.get("quality_gates"))
            if skill_quality_gates:
                quality_gates.extend(skill_quality_gates)
                acknowledgement_required_gates.extend(skill_quality_gates)
                _add_source_ref(
                    source_refs,
                    "quality_gates",
                    f"skill.{skill_id}.quality_gates",
                )

        must_rules = [
            "Do not write canonical workspace state directly.",
            "Do not fabricate sources, citations, experiment results, or code execution outcomes.",
        ]
        citation_policy = _as_dict(definition.get("citation_policy"))
        if citation_policy.get("required_for_prism_manuscript"):
            must_rules.append(
                "When Prism manuscript output requires citations, preserve citation gaps instead of inventing citation keys."
            )
        review_policy = _as_dict(definition.get("review_policy"))
        if review_policy.get("require_user_acceptance", True):
            must_rules.append("Stage outputs for user review before commit.")

        should_rules = [
            *_string_list(template.quality_expectations),
            *_mission_should_rules(definition),
        ]

        return ResolvedQualityContract(
            capability_id=str(getattr(capability, "id", "") or ""),
            template_id=template.id,
            skill_ids=list(effective_skill_ids),
            role=template.display_role,
            output_contracts=_dedupe(_string_list(template.output_contracts)),
            output_schema=output_schema,
            quality_gates=_dedupe(quality_gates),
            acknowledgement_required_gates=_dedupe(acknowledgement_required_gates),
            quality_expectations=_dedupe(_string_list(template.quality_expectations)),
            must_rules=_dedupe(must_rules),
            should_rules=_dedupe(should_rules),
            may_rules=[],
            recruitment_hints=_recruitment_hints(team_policy),
            source_refs=source_refs,
        )

    @staticmethod
    def _skill_contract_data(skill: Any) -> dict[str, Any]:
        skill_json = _as_dict(getattr(skill, "skill_json", None))
        config = _as_dict(getattr(skill, "config", None))
        if skill_json:
            merged = dict(config)
            merged.update(skill_json)
            return merged
        return config


def _mission_should_rules(definition: dict[str, Any]) -> list[str]:
    mission = _as_dict(definition.get("mission"))
    allowed_deliverables = _string_list(mission.get("allowed_deliverables"))
    if not allowed_deliverables:
        return []
    return [
        "Keep deliverables within mission.allowed_deliverables: "
        + ", ".join(allowed_deliverables)
    ]


def _recruitment_hints(team_policy: CapabilityTeamPolicy) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {}
    for key, raw_templates in team_policy.recruitment_triggers.items():
        templates = _string_list(raw_templates)
        if templates:
            hints[str(key)] = _dedupe(templates)
    return hints


def _merge_object_schemas(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    result = _empty_object_schema()
    left_properties = _as_dict(left.get("properties"))
    right_properties = _as_dict(right.get("properties"))
    result["properties"] = {
        **left_properties,
        **right_properties,
    }
    result["required"] = _dedupe(
        [
            *_string_list(left.get("required")),
            *_string_list(right.get("required")),
        ]
    )
    return result


def _empty_object_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


def _add_source_ref(
    refs: dict[str, list[str]],
    key: str,
    value: str,
) -> None:
    values = refs.setdefault(key, [])
    if value not in values:
        values.append(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
