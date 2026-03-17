"""Tests for copyright_materials sub-graph helper functions."""

import pytest

from src.agents.graphs.software_copyright.copyright_materials import (
    _build_required_materials,
    _build_review_checklist,
    _normalize_list,
)


class TestNormalizeList:
    def test_string_to_list(self):
        result = _normalize_list("a, b,c")
        assert result == ["a", "b", "c"]

    def test_list_with_empty_strings(self):
        result = _normalize_list(["a", "", "  c", ""])
        assert result == ["c"]

    def test_empty_string(self):
        result = _normalize_list("")
        assert result == []

    def test_none_value(self):
        result = _normalize_list(None)
        assert result == []

    def test_non_string_non_list(self):
        result = _normalize_list(123)
        assert result == []

    def test_mixed_content(self):
        result = _normalize_list(["a", "", "b,c", None])
        assert result == ["a", "b,c"]

    def test_integer_list(self):
        result = _normalize_list([1, 2, 3])
        assert result == ["1", "2", "3"]


class TestBuildRequiredMaterials:
    def test_basic_materials(self):
        result = _build_required_materials(
            software_name="Test Software",
            version="V2.0",
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
        assert "Feature 1" in app_form["required_fields"][0]
        assert "Feature 2" in app_form["required_fields"][1]
        assert "2024-01-01" in app_form["required_fields"][2]
        assert app_form["status"] == "pending"

        # Verify source code excerpt
        source_code = result[1]
        assert source_code["id"] == "source_code_excerpt"
        assert source_code["title"] == "源程序连续页"
        assert source_code["status"] == "pending"
        assert len(source_code["required_fields"]) == 3
        assert "准备前后各连续 30 页代码样本" in source_code["required_fields"][0]
        assert source_code["suggested_modules"] == ["Core", "UI"]

        # Verify manual excerpt
        manual = result[2]
        assert manual["id"] == "manual_excerpt"
        assert manual["title"] == "软件说明书/操作手册"
        assert manual["status"] == "pending"
        assert len(manual["required_fields"]) == 4

        assert "包含软件简介" in manual["required_fields"][0]

        # Verify identity_support
        identity = result[3]
        assert identity["id"] == "identity_support"
        assert identity["title"] == "主体与权属证明材料"
        assert identity["status"] == "pending"
        assert len(identity["required_fields"]) == 3

        # Verify feature summary
        feature_summary = result[4]
        assert feature_summary["id"] == "feature_summary"
        assert feature_summary["title"] == "软件功能亮点归纳"
        assert feature_summary["status"] == "draft"
        assert feature_summary["required_fields"] == ["Feature 1", "Feature 2"]
        assert feature_summary["platforms"] == ["Web", "Mobile"] or ["Web", "Desktop", "Server"]
        target_platforms = feature_summary["platforms"]
        assert target_platforms == ["Web", "Mobile", "Server"]


class TestBuildReviewChecklist:
    def test_review_checklist_content(self):
        materials = _build_required_materials(
            software_name="Test Software",
            version="V2.0",
            applicant_name="Test Company",
            completion_date="2024-01-01",
            highlights=["Feature 1"],
            target_platforms=["Web", "Mobile"],
            source_modules=["Core", "UI"],
        )
        checklist = _build_review_checklist(materials)
        assert len(checklist) == 4
        assert all("软件名称" in item for item in checklist)
        assert all("版本号" in item for item in checklist)
        assert all("申请人" in item for item in checklist
        assert all("一致" in item.lower() for item in checklist
