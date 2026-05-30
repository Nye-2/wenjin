from types import SimpleNamespace

from src.agents.lead_agent.v2.team.contracts import (
    AgentTemplate,
    CapabilityTeamPolicy,
)
from src.agents.lead_agent.v2.team.quality_contract import QualityContractResolver
from src.dataservice_client.contracts.catalog import CapabilitySkillPayload


def _capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="team_research",
        display_name="团队调研",
        definition_json={
            "mission": {
                "primary_surface": "prism",
                "allowed_deliverables": ["literature_evidence_report"],
            },
            "review_policy": {"require_user_acceptance": True},
            "citation_policy": {
                "source_scope": "workspace_library",
                "required_for_prism_manuscript": True,
            },
            "sandbox_policy": {"mode": "none"},
            "quality_gates": ["evidence_traceability"],
        },
    )


def _team_policy() -> CapabilityTeamPolicy:
    return CapabilityTeamPolicy(
        core_templates=["research_scout.v1"],
        optional_templates=["critical_reviewer.v1"],
        quality_pipeline=["evidence_traceability"],
        recruitment_triggers={
            "missing_sources": ["research_scout.v1"],
            "unsupported_claims": ["critical_reviewer.v1"],
        },
    )


def _template(*, category: str = "research") -> AgentTemplate:
    return AgentTemplate(
        id="research_scout.v1",
        display_role="文献检索员",
        category=category,
        description="Research role",
        persona_prompt="research",
        default_skills=["research-scout", "citation-auditor"],
        risk_profile={"room_write": "staged_only"},
        output_contracts=["literature_evidence_report.v1"],
        quality_expectations=["claims map to source ids"],
    )


def _skill(
    skill_id: str,
    *,
    required: list[str],
    quality_gates: list[str],
) -> CapabilitySkillPayload:
    return CapabilitySkillPayload(
        id=skill_id,
        display_name=skill_id,
        worker_type="research",
        subagent_type="team_fake",
        prompt="Return structured evidence.",
        skill_json={
            "schema_version": "capability_skill.v2",
            "id": skill_id,
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": required,
                    "properties": {
                        "text": {"type": "string"},
                        "quality_gates_checked": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "sources": {"type": "array"},
                    },
                },
            },
            "quality_gates": quality_gates,
        },
    )


def test_quality_contract_resolver_merges_existing_catalog_records() -> None:
    contract = QualityContractResolver.resolve(
        capability=_capability(),
        template=_template(),
        team_policy=_team_policy(),
        effective_skill_ids=["research-scout", "citation-auditor"],
        skill_records={
            "research-scout": _skill(
                "research-scout",
                required=["text", "quality_gates_checked"],
                quality_gates=["no_fabricated_sources", "source_log_required"],
            ),
            "citation-auditor": _skill(
                "citation-auditor",
                required=["sources", "quality_gates_checked"],
                quality_gates=["source_log_required"],
            ),
        },
    )

    assert contract.schema_version == "resolved_quality_contract.v1"
    assert contract.capability_id == "team_research"
    assert contract.template_id == "research_scout.v1"
    assert contract.skill_ids == ["research-scout", "citation-auditor"]
    assert contract.role == "文献检索员"
    assert contract.output_contracts == ["literature_evidence_report.v1"]
    assert contract.output_schema["type"] == "object"
    assert contract.output_schema["required"] == [
        "text",
        "quality_gates_checked",
        "sources",
    ]
    assert contract.quality_gates == [
        "evidence_traceability",
        "no_fabricated_sources",
        "source_log_required",
    ]
    assert contract.acknowledgement_required_gates == [
        "no_fabricated_sources",
        "source_log_required",
    ]
    assert contract.quality_expectations == ["claims map to source ids"]
    assert "Do not write canonical workspace state directly." in contract.must_rules
    assert "Do not fabricate sources, citations, experiment results, or code execution outcomes." in contract.must_rules
    assert contract.recruitment_hints["missing_sources"] == ["research_scout.v1"]
    assert contract.recruitment_hints["unsupported_claims"] == ["critical_reviewer.v1"]
    assert contract.source_refs["quality_gates"] == [
        "team_policy.quality_pipeline",
        "capability.quality_gates",
        "skill.research-scout.quality_gates",
        "skill.citation-auditor.quality_gates",
    ]


def test_quality_contract_resolver_reads_legacy_skill_config() -> None:
    skill = CapabilitySkillPayload(
        id="legacy-skill",
        display_name="Legacy Skill",
        worker_type="research",
        subagent_type="team_fake",
        config={
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                },
            },
            "quality_gates": ["legacy_gate"],
        },
    )

    contract = QualityContractResolver.resolve(
        capability=_capability(),
        template=_template(),
        team_policy=_team_policy(),
        effective_skill_ids=["legacy-skill"],
        skill_records={"legacy-skill": skill},
    )

    assert contract.output_schema["required"] == ["text"]
    assert "legacy_gate" in contract.quality_gates
    assert contract.source_refs["output_schema"] == ["skill.legacy-skill.io_contract.output_schema"]


def test_quality_contract_resolver_ignores_missing_skill_records() -> None:
    contract = QualityContractResolver.resolve(
        capability=_capability(),
        template=_template(),
        team_policy=_team_policy(),
        effective_skill_ids=["missing-skill"],
        skill_records={"missing-skill": None},
    )

    assert contract.skill_ids == ["missing-skill"]
    assert contract.output_schema == {"type": "object", "properties": {}, "required": []}
    assert contract.quality_gates == ["evidence_traceability"]


def test_quality_contract_resolver_auto_merges_contract_overlay_skill() -> None:
    overlay = CapabilitySkillPayload(
        id="sci-journal-rules",
        display_name="SCI Journal Rules",
        worker_type="domain_overlay",
        subagent_type="team_fake",
        prompt="Check SCI journal requirements.",
        skill_json={
            "schema_version": "capability_skill.v2",
            "id": "sci-journal-rules",
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": [
                        "text",
                        "quality_gates_checked",
                        "checked_requirements",
                    ],
                    "properties": {
                        "text": {"type": "string"},
                        "quality_gates_checked": {"type": "array"},
                        "checked_requirements": {"type": "array"},
                    },
                },
            },
            "quality_gates": ["reporting_guideline_checked"],
        },
    )

    contract = QualityContractResolver.resolve(
        capability=_capability(),
        template=_template(category="review"),
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            contract_overlay_skills=["sci-journal-rules"],
            contract_overlay_categories=["review"],
        ),
        effective_skill_ids=["research-scout"],
        skill_records={
            "research-scout": _skill(
                "research-scout",
                required=["text", "quality_gates_checked"],
                quality_gates=["source_log_required"],
            ),
            "sci-journal-rules": overlay,
        },
    )

    assert contract.skill_ids == ["research-scout", "sci-journal-rules"]
    assert "reporting_guideline_checked" in contract.quality_gates
    assert "checked_requirements" in contract.output_schema["required"]
    assert contract.source_refs["skill_ids"] == ["team_policy.contract_overlay_skills"]


def test_quality_contract_resolver_skips_contract_overlay_for_other_categories() -> None:
    overlay = CapabilitySkillPayload(
        id="sci-journal-rules",
        display_name="SCI Journal Rules",
        worker_type="domain_overlay",
        subagent_type="team_fake",
        prompt="Check SCI journal requirements.",
        skill_json={
            "schema_version": "capability_skill.v2",
            "id": "sci-journal-rules",
            "quality_gates": ["format_requirements_checked"],
        },
    )

    contract = QualityContractResolver.resolve(
        capability=_capability(),
        template=_template(category="research"),
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            contract_overlay_skills=["sci-journal-rules"],
            contract_overlay_categories=["review", "writing"],
        ),
        effective_skill_ids=["research-scout"],
        skill_records={
            "research-scout": _skill(
                "research-scout",
                required=["text", "quality_gates_checked"],
                quality_gates=["source_log_required"],
            ),
            "sci-journal-rules": overlay,
        },
    )

    assert contract.skill_ids == ["research-scout"]
    assert "format_requirements_checked" not in contract.quality_gates
    assert "skill_ids" not in contract.source_refs
