"""Tests for copyright_materials sub-graph helper functions."""

import pytest

from src.agents.graphs._shared import _normalize_list
from src.agents.graphs.software_copyright.copyright_materials import (
    _build_required_materials,
    _build_review_checklist,
)


class TestNormalizeList:
    def test_string_to_list(self):
        result = _normalize_list("a, b,c")
        assert result == ["a", "b", "c"]

    def test_list_with_empty_strings(self):
        result = _normalize_list(["a", "", "  c", ""])
        assert result == ["a", "c"]

    def test_empty_string(self):
        result = _normalize_list("")
        assert result == []

    def test_none_value(self):
        result = _normalize_list(None)
        assert result == []

    def test_non_string_non_list(self):
        result = _normalize_list(123)
        assert result == []

    def test_max_items_limit(self):
        result = _normalize_list("1,2,3,4,5,6,7,8,9,10,11,12", max_items=5)
        assert len(result) == 5


class TestBuildRequiredMaterials:
    def test_basic_materials(self):
        result = _build_required_materials(
            software_name="Test Software",
            version="V1.0",
            applicant_name="Test Company",
            completion_date="2024-01-01",
            highlights=["Feature 1", "Feature 2"],
            target_platforms=["Web", "Mobile"],
            source_modules=["Core", "UI"],
        )

        assert len(result) == 5

        # Verify application form
        app_form = result[0]
        assert app_form["id"] == "application_form"
        assert app_form["title"] == "软件著作权登记申请表"
        assert app_form["status"] == "pending"
        assert "Test Software" in app_form["required_fields"][0]
        assert "V1.0" in app_form["required_fields"][1]
        assert "Test Company" in app_form["required_fields"][2]
        assert "2024-01-01" in app_form["required_fields"][3]

        # Verify source code excerpt
        source_code = result[1]
        assert source_code["id"] == "source_code_excerpt"
        assert source_code["title"] == "源程序连续页"
        assert source_code["status"] == "pending"
        assert source_code["suggested_modules"] == ["Core", "UI"]

        # Verify manual excerpt
        manual = result[2]
        assert manual["id"] == "manual_excerpt"
        assert manual["title"] == "软件说明书/操作手册"
        assert manual["status"] == "pending"

        # Verify identity_support
        identity = result[3]
        assert identity["id"] == "identity_support"
        assert identity["title"] == "主体与权属证明材料"
        assert identity["status"] == "pending"

        # Verify feature summary
        feature_summary = result[4]
        assert feature_summary["id"] == "feature_summary"
        assert feature_summary["title"] == "软件功能亮点归纳"
        assert feature_summary["status"] == "draft"
        assert feature_summary["required_fields"] == ["Feature 1", "Feature 2"]
        assert feature_summary["platforms"] == ["Web", "Mobile"]


class TestBuildReviewChecklist:
    def test_review_checklist_content(self):
        checklist = _build_review_checklist()
        assert len(checklist) == 4
        # Verify key content
        assert any("软件名称" in item for item in checklist)
        assert any("版本号" in item for item in checklist)
        assert any("申请人" in item or "主体" in item for item in checklist)
        assert any("一致" in item for item in checklist)


class TestCopyrightMaterialsGraph:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic graph execution with minimal payload."""
        from src.agents.graphs.software_copyright.copyright_materials import (
            copyright_materials_graph,
        )

        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "software_copyright",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "Test Software",
            "params": {
                "software_name": "Test Software",
                "version": "V1.0",
                "applicant_name": "Test Company",
            },
        }

        result = await copyright_materials_graph(initial_state, payload)

        assert "schema_version" in result
        assert "required_materials" in result
        assert "review_checklist" in result
        assert result["schema_version"] == "v1"
        assert len(result["required_materials"]) == 5

    @pytest.mark.asyncio
    async def test_fallback_to_workspace_name(self):
        """Test that software_name falls back to workspace name."""
        from src.agents.graphs.software_copyright.copyright_materials import (
            copyright_materials_graph,
        )

        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "software_copyright",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "My Awesome Software",
            "params": {},
        }

        result = await copyright_materials_graph(initial_state, payload)

        assert "software_profile" in result
        assert result["software_profile"]["software_name"] == "My Awesome Software"
