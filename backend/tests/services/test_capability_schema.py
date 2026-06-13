"""Tests for capability/skill YAML schema validation."""

import pytest
from pydantic import ValidationError

from src.services.capability_schema import (
    CapabilitySkillV2YamlModel,
    CapabilitySkillYamlModel,
    CapabilityV2YamlModel,
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


class TestCapabilityV2Yaml:
    def _valid_payload(self) -> dict:
        return {
            "schema_version": "capability.v2",
            "id": "idea_to_thesis_manuscript",
            "workspace_type": "thesis",
            "enabled": True,
            "display": {
                "name": "Idea 到论文全文",
                "description": "根据已确认 idea 生成或更新完整论文主稿",
                "icon": "file-pen",
                "color": "blue",
                "order": 10,
                "entry_tier": "primary",
            },
            "intent": {
                "description": "用户有明确研究 idea，希望生成或更新完整论文主稿",
                "trigger_phrases": ["写全文", "根据 idea 写论文"],
            },
            "mission": {
                "goal": "produce_or_update_primary_document",
                "primary_surface": "prism",
                "document_role": "primary_manuscript",
                "user_promise": "生成可审阅、可回滚、带来源追踪的主文档变更",
                "allowed_deliverables": ["full_document_update"],
            },
            "inputs": {
                "required_decisions": [
                    {
                        "key": "research_idea",
                        "ask": "你的核心研究 idea 是什么？",
                        "type": "string",
                        "persist_as": "decision",
                    }
                ],
                "brief_schema": {
                    "type": "object",
                    "required": ["research_idea"],
                    "properties": {"research_idea": {"type": "string"}},
                },
            },
            "context_policy": {
                "room_reads": {"library": "summary", "documents": "excerpts"},
                "prism_context": {"include_outline": True},
                "full_text_access": "explicit_tool_only",
            },
            "sandbox_policy": {
                "mode": "conditional",
                "profiles": ["analysis", "visualization"],
                "allowed_operations": ["run_python", "render_figures"],
                "isolation": {
                    "provider": "docker",
                    "network": "default_deny_allowlist",
                },
                "resource_limits": {"cpu": 2, "memory_mb": 4096},
                "artifact_policy": {"review_required": True},
            },
            "review_policy": {
                "default_targets": ["prism_file_change", "sandbox_artifact"],
                "require_user_acceptance": True,
                "allow_bulk_accept": True,
            },
            "quality_gates": [
                "no_direct_primary_document_write",
                "provenance_required_for_claims",
            ],
            "graph_template": {"phases": []},
        }

    def test_minimal_valid_v2(self):
        model = CapabilityV2YamlModel(**self._valid_payload())

        assert model.schema_version == "capability.v2"
        assert model.display.entry_tier == "primary"
        assert model.sandbox_policy.mode == "conditional"

    def test_missing_schema_version_fails(self):
        payload = self._valid_payload()
        payload.pop("schema_version")

        with pytest.raises(ValidationError):
            CapabilityV2YamlModel(**payload)

    def test_rejects_extra_fields(self):
        payload = self._valid_payload()
        payload["runtime"] = {"requires_sandbox": True}

        with pytest.raises(ValidationError):
            CapabilityV2YamlModel(**payload)

    def test_rejects_forbidden_sandbox_isolation_controls(self):
        payload = self._valid_payload()
        payload["sandbox_policy"]["isolation"]["allow_docker_socket"] = True

        with pytest.raises(ValidationError, match="forbidden host/container controls"):
            CapabilityV2YamlModel(**payload)

    def test_to_catalog_data_derives_read_model_fields(self):
        model = CapabilityV2YamlModel(**self._valid_payload())
        data = model.to_catalog_data()

        assert data["display_name"] == "Idea 到论文全文"
        assert data["trigger_phrases"] == ["写全文", "根据 idea 写论文"]
        assert data["brief_schema"]["required"] == ["research_idea"]
        assert data["ui_meta"]["entry_tier"] == "primary"
        assert data["runtime"]["sandbox_policy"]["mode"] == "conditional"

    def test_citation_policy_round_trips_to_catalog_data(self):
        payload = self._valid_payload()
        payload["citation_policy"] = {
            "source_scope": "workspace_library",
            "required_for_prism_manuscript": True,
            "allowed_commands": ["cite", "citep", "citet"],
            "bibliography_file": "refs.bib",
            "bibliography_command": "\\bibliography{refs}",
            "missing_key_behavior": "block_prism_stage",
            "record_usage": True,
        }

        model = CapabilityV2YamlModel(**payload)
        data = model.to_catalog_data()

        assert data["citation_policy"]["source_scope"] == "workspace_library"
        assert data["citation_policy"]["bibliography_file"] == "refs.bib"
        assert data["citation_policy"]["missing_key_behavior"] == "block_prism_stage"
        assert data["citation_policy"]["record_usage"] is True

    def test_citation_policy_rejects_invalid_missing_key_behavior(self):
        payload = self._valid_payload()
        payload["citation_policy"] = {
            "missing_key_behavior": "silently_ignore",
        }

        with pytest.raises(ValidationError):
            CapabilityV2YamlModel(**payload)

    def test_team_kernel_requires_quality_pipeline(self):
        payload = self._valid_payload()
        payload["runtime"] = {
            "mode": "team_kernel",
            "allowed_tools": ["web_search"],
        }
        payload["team_policy"] = {
            "core_templates": ["research_scout.v1"],
            "optional_templates": [],
            "capability_tools": ["web_search"],
            "quality_pipeline": [],
        }

        with pytest.raises(ValidationError, match="quality_pipeline"):
            CapabilityV2YamlModel(**payload)

    def test_team_policy_accepts_contract_overlays(self):
        payload = self._valid_payload()
        payload["runtime"] = {
            "mode": "team_kernel",
            "allowed_tools": ["web_search"],
        }
        payload["team_policy"] = {
            "core_templates": ["research_scout.v1"],
            "optional_templates": [],
            "capability_tools": ["web_search"],
            "contract_overlay_skills": ["sci-journal-rules"],
            "contract_overlay_categories": ["review", "writing"],
            "quality_pipeline": ["evidence_traceability"],
        }

        model = CapabilityV2YamlModel(**payload)
        data = model.to_catalog_data()

        assert data["team_policy"]["contract_overlay_skills"] == ["sci-journal-rules"]
        assert data["team_policy"]["contract_overlay_categories"] == ["review", "writing"]

    def test_team_presentation_extension_is_validated(self):
        payload = self._valid_payload()
        payload["extensions"] = {
            "team_presentation": {
                "template_overrides": {
                    "literature_synthesizer.v1": {
                        "public_name": "综述姐 Athena",
                        "status_phrases": {"running": "织主题矩阵中"},
                    }
                },
            }
        }

        model = CapabilityV2YamlModel(**payload)
        data = model.to_catalog_data()

        presentation = data["extensions"]["team_presentation"]
        assert presentation["schema_version"] == "wenjin.team.presentation.v1"
        assert presentation["template_overrides"]["literature_synthesizer.v1"]["public_name"] == "综述姐 Athena"

    def test_team_presentation_extension_rejects_leader_virtual_member(self):
        payload = self._valid_payload()
        payload["extensions"] = {
            "team_presentation": {
                "leader_virtual_member": {
                    "public_name": "Steve",
                    "role_title": "研究负责人",
                }
            }
        }

        with pytest.raises(ValidationError, match="leader_virtual_member"):
            CapabilityV2YamlModel(**payload)

    def test_team_presentation_extension_rejects_non_display_fields(self):
        payload = self._valid_payload()
        payload["extensions"] = {
            "team_presentation": {
                "template_overrides": {
                    "research_scout.v1": {
                        "public_name": "文献猎手 Nora",
                        "default_skills": ["web_search"],
                    }
                }
            }
        }

        with pytest.raises(ValidationError, match="default_skills"):
            CapabilityV2YamlModel(**payload)

    def test_quality_gate_ids_must_not_be_blank(self):
        payload = self._valid_payload()
        payload["quality_gates"] = [" "]

        with pytest.raises(ValidationError, match="quality_gates"):
            CapabilityV2YamlModel(**payload)

    def test_research_evidence_required_surfaces_must_be_known(self):
        payload = self._valid_payload()
        payload["research_evidence"] = {
            "required_surfaces": ["workflow_trace", "unknown_surface"],
        }

        with pytest.raises(ValidationError, match="unknown research evidence surfaces"):
            CapabilityV2YamlModel(**payload)

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


class TestCapabilitySkillV2Yaml:
    def _valid_payload(self) -> dict:
        return {
            "schema_version": "capability_skill.v2",
            "id": "evidence-analyst",
            "enabled": True,
            "display_name": "Evidence Analyst",
            "description": "在 sandbox 中完成数据分析、统计检验、图表和结果说明",
            "worker": {
                "category": "evidence",
                "subagent_type": "react",
                "role_prompt": "Run reproducible analysis and return artifacts.",
            },
            "io_contract": {
                "input_schema": {
                    "type": "object",
                    "required": ["analysis_goal"],
                },
                "output_schema": {
                    "type": "object",
                    "required": ["artifacts", "quality_gates_checked"],
                    "properties": {
                        "artifacts": {"type": "array"},
                        "quality_gates_checked": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "context_access": {
                "room_reads": {"documents": "excerpts", "decisions": "relevant"},
                "prism_context": "summary",
            },
            "tool_policy": {
                "allowed_tools": ["sandbox.run_python", "sandbox.write_file"],
            },
            "sandbox_access": {
                "mode": "required",
                "profiles": ["analysis", "visualization"],
            },
            "quality_gates": ["all_artifacts_have_input_hashes"],
            "extensions": {
                "search": {
                    "sources": ["semantic_scholar"],
                    "max_results": 10,
                }
            },
        }

    def test_minimal_valid_v2(self):
        model = CapabilitySkillV2YamlModel(**self._valid_payload())

        assert model.schema_version == "capability_skill.v2"
        assert model.subagent_type == "react"
        assert model.sandbox_access.mode == "required"

    def test_missing_schema_version_fails(self):
        payload = self._valid_payload()
        payload.pop("schema_version")

        with pytest.raises(ValidationError):
            CapabilitySkillV2YamlModel(**payload)

    def test_rejects_extra_fields(self):
        payload = self._valid_payload()
        payload["config"] = {"output_kind": "document"}

        with pytest.raises(ValidationError):
            CapabilitySkillV2YamlModel(**payload)

    def test_to_catalog_data_derives_read_model_fields(self):
        model = CapabilitySkillV2YamlModel(**self._valid_payload())
        data = model.to_catalog_data()

        assert data["worker_type"] == "evidence"
        assert data["subagent_type"] == "react"
        assert data["prompt"] == "Run reproducible analysis and return artifacts."
        assert data["allowed_tools"] == ["sandbox.run_python", "sandbox.write_file"]
        assert data["config"]["extensions"]["search"]["sources"] == ["semantic_scholar"]

    def test_skill_with_quality_gates_requires_checked_output_field(self):
        payload = self._valid_payload()
        payload["quality_gates"] = ["source_log_required"]
        payload["io_contract"]["output_schema"] = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
        }

        with pytest.raises(ValidationError, match="quality_gates_checked"):
            CapabilitySkillV2YamlModel(**payload)

    def test_skill_with_quality_gates_requires_checked_field_to_be_required(self):
        payload = self._valid_payload()
        payload["quality_gates"] = ["source_log_required"]
        payload["io_contract"]["output_schema"] = {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "quality_gates_checked": {"type": "array"},
            },
        }

        with pytest.raises(ValidationError, match="quality_gates_checked"):
            CapabilitySkillV2YamlModel(**payload)

    def test_skill_output_schema_must_be_object_when_declared(self):
        payload = self._valid_payload()
        payload["io_contract"]["output_schema"] = {"type": "array"}

        with pytest.raises(ValidationError, match="output_schema"):
            CapabilitySkillV2YamlModel(**payload)
