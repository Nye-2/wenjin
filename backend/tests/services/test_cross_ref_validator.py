"""Tests for cross-reference validation across capability + skill + registry."""

import pytest

from src.services.capability_schema import CapabilityV2YamlModel, CrossRefValidator


def _make_capability_yaml(
    skill_ids: list[str], subagent_types: list[str]
) -> CapabilityV2YamlModel:
    return CapabilityV2YamlModel(
        schema_version="capability.v2",
        id="idea_to_thesis_manuscript",
        workspace_type="thesis",
        display={
            "name": "Idea 到论文全文",
            "description": "x",
            "icon": "file-pen",
            "color": "blue",
            "order": 10,
            "entry_tier": "primary",
        },
        intent={"description": "x", "trigger_phrases": ["写全文"]},
        mission={
            "goal": "produce_or_update_primary_document",
            "primary_surface": "prism",
            "document_role": "primary_manuscript",
            "user_promise": "x",
            "allowed_deliverables": ["full_document_update"],
        },
        inputs={"required_decisions": [], "brief_schema": {"type": "object"}},
        context_policy={"room_reads": {}, "prism_context": {}, "full_text_access": "explicit_tool_only"},
        sandbox_policy={"mode": "none", "profiles": [], "allowed_operations": []},
        review_policy={
            "default_targets": ["prism_file_change"],
            "require_user_acceptance": True,
            "allow_bulk_accept": True,
        },
        quality_gates=["no_direct_primary_document_write"],
        graph_template={
            "phases": [
                {
                    "name": "p",
                    "tasks": [
                        {"name": f"t{i}", "subagent_type": st, "skill_id": sid}
                        for i, (st, sid) in enumerate(
                            zip(subagent_types, skill_ids, strict=False)
                        )
                    ],
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_skill_id_missing_fails(monkeypatch):
    async def fake_existing_skill_ids(_ids):
        return set()  # no skills exist

    monkeypatch.setattr(
        CrossRefValidator,
        "_existing_skill_ids",
        staticmethod(fake_existing_skill_ids),
    )
    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    cap = _make_capability_yaml(
        skill_ids=["literature-reviewer"], subagent_types=["react"]
    )
    errors = await CrossRefValidator().validate_capability(cap)
    assert any("literature-reviewer" in e for e in errors)


@pytest.mark.asyncio
async def test_subagent_type_unknown_fails(monkeypatch):
    async def fake_existing(ids):
        return set(ids)

    monkeypatch.setattr(
        CrossRefValidator,
        "_existing_skill_ids",
        staticmethod(fake_existing),
    )
    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    cap = _make_capability_yaml(
        skill_ids=["any-skill"], subagent_types=["nonexistent"]
    )
    errors = await CrossRefValidator().validate_capability(cap)
    assert any("nonexistent" in e for e in errors)


@pytest.mark.asyncio
async def test_skill_subagent_type_validated(monkeypatch):
    from src.services.capability_schema import CapabilitySkillV2YamlModel

    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    skill = CapabilitySkillV2YamlModel(
        schema_version="capability_skill.v2",
        id="x",
        display_name="X",
        worker={
            "category": "writing",
            "subagent_type": "bogus",
            "role_prompt": "Write.",
        },
        io_contract={"input_schema": {}, "output_schema": {}},
        context_access={"room_reads": {}, "prism_context": "summary"},
        tool_policy={"allowed_tools": []},
        sandbox_access={"mode": "none", "profiles": []},
        quality_gates=[],
    )
    errors = await CrossRefValidator().validate_skill(skill)
    assert any("bogus" in e for e in errors)


@pytest.mark.asyncio
async def test_skill_v2_subagent_type_validated(monkeypatch):
    from src.services.capability_schema import CapabilitySkillV2YamlModel

    monkeypatch.setattr(
        CrossRefValidator,
        "_registry_subagent_types",
        staticmethod(lambda: {"react"}),
    )

    skill = CapabilitySkillV2YamlModel(
        schema_version="capability_skill.v2",
        id="evidence-analyst",
        display_name="Evidence Analyst",
        worker={
            "category": "evidence",
            "subagent_type": "bogus",
            "role_prompt": "Run reproducible analysis.",
        },
        io_contract={"input_schema": {}, "output_schema": {}},
        context_access={"room_reads": {}, "prism_context": "summary"},
        tool_policy={"allowed_tools": []},
        sandbox_access={"mode": "required", "profiles": ["analysis"]},
        quality_gates=[],
    )
    errors = await CrossRefValidator().validate_skill(skill)
    assert any("bogus" in e for e in errors)
