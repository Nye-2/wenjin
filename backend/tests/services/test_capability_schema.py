"""Tests for capability/skill YAML schema validation."""

import pytest
from pydantic import ValidationError

from src.services.capability_schema import (
    CapabilitySkillYamlModel,
    CapabilityYamlModel,
    UIMetaModel,
)


class TestUIMeta:
    def test_minimal_valid(self):
        m = UIMetaModel(icon="search", color="purple")
        assert m.order == 0
        assert m.stages == []
        assert m.follow_up_prompt is None

    def test_with_stages(self):
        m = UIMetaModel(
            icon="search",
            color="purple",
            stages=[{"id": "s1", "label": "step 1"}],
        )
        assert len(m.stages) == 1
        assert m.stages[0].id == "s1"


class TestCapabilityYaml:
    def test_minimal_valid(self):
        m = CapabilityYamlModel(
            id="test_cap",
            workspace_type="thesis",
            display_name="Test",
            intent_description="test",
            brief_schema={"type": "object"},
            graph_template={"phases": []},
            ui_meta={"icon": "search", "color": "purple"},
        )
        assert m.enabled is True
        assert m.trigger_phrases == []

    def test_missing_required_field_fails(self):
        with pytest.raises(ValidationError):
            CapabilityYamlModel(
                id="x",
                workspace_type="thesis",
                display_name="X",
                intent_description="x",
                brief_schema={},
                graph_template={},
                # ui_meta missing
            )

    def test_required_decision_type_validated(self):
        with pytest.raises(ValidationError):
            CapabilityYamlModel(
                id="x",
                workspace_type="thesis",
                display_name="X",
                intent_description="x",
                brief_schema={},
                graph_template={},
                ui_meta={"icon": "x", "color": "x"},
                required_decisions=[
                    {"key": "k", "ask": "?", "type": "object"}
                ],  # invalid
            )


class TestCapabilitySkillYaml:
    def test_minimal_valid(self):
        m = CapabilitySkillYamlModel(
            id="test-skill",
            display_name="Test Skill",
            subagent_type="react",
        )
        assert m.enabled is True
        assert m.prompt == ""
        assert m.allowed_tools == []
