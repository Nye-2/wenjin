"""Tests for proposal_outline sub-graph helper functions."""

from src.agents.graphs.proposal.proposal_outline import (
    _build_milestones,
    _build_proposal_template_sections,
    _build_risks,
    _build_schedule_template,
    _normalize_llm_sections,
    _normalize_period,
    _normalize_proposal_type,
    _parse_json_response,
)


class TestNormalizeProposalType:
    def test_national_natural_science(self):
        result = _normalize_proposal_type("national_natural_science")
        assert result == "national_natural_science"

    def test_national_social_science(self):
        result = _normalize_proposal_type("national_social_science")
        assert result == "national_social_science"

    def test_provincial(self):
        result = _normalize_proposal_type("provincial")
        assert result == "provincial"

    def test_enterprise(self):
        result = _normalize_proposal_type("enterprise")
        assert result == "enterprise"

    def test_university(self):
        result = _normalize_proposal_type("university")
        assert result == "university"

    def test_other(self):
        result = _normalize_proposal_type("other")
        assert result == "other"

    def test_chinese_alias(self):
        result = _normalize_proposal_type("国自然")
        assert result == "national_natural_science"

    def test_english_alias(self):
        result = _normalize_proposal_type("nsfc")
        assert result == "national_natural_science"

    def test_unknown_type(self):
        result = _normalize_proposal_type("unknown_type")
        assert result == "other"

    def test_empty_type(self):
        result = _normalize_proposal_type("")
        assert result == "other"

    def test_none_type(self):
        result = _normalize_proposal_type(None)
        assert result == "other"


class TestNormalizePeriod:
    def test_none_uses_default(self):
        result = _normalize_period(None, "national_natural_science")
        assert result == 36

    def test_int_value(self):
        result = _normalize_period(24, "provincial")
        assert result == 24

    def test_string_value(self):
        result = _normalize_period("36", "enterprise")
        assert result == 36

    def test_invalid_value(self):
        result = _normalize_period("invalid", "other")
        assert result == 24


class TestBuildScheduleTemplate:
    def test_short_period(self):
        result = _build_schedule_template(12)
        assert "项目周期： 12个月" in result
        assert len(result.split("\n")) == 4  # 4 phases

        lines = result.split("\n")
        assert "第1-3月" in lines[1]
        assert "第10-12月" in lines[-1]

        "period, time, task = phases[0]
        assert period == "第1-3月"
        assert task == "文献调研与方案设计"

        "period, time, task in phases[1]
        assert period == "第4-6月"
        assert task == "实验/研究实施"

        "period, time, task in phases[2]
        assert period == "第7-9月"
        assert task == "数据分析与结果整理"
        "period, time, task in phases[3]
        assert period == "第10-12月"
        assert task == "报告撰写与成果总结"

        "period, time, task in phases[4]
        assert "第4-6月" in period
        assert "实验/研究实施" in task

        "period, time, task in phases[4]
        assert "第7-9月" in period
        assert "数据分析与结果整理" in task

        "period, time, task in phases[5]
        assert "第10-12月" in period
        assert "报告撰写与成果总结" in task

        "assert phases[0][2] == ("第1-3月", "文献调研与方案设计")
        assert phases[0][3] == ("第4-6月", "实验/研究实施")
        assert phases[0][4] == ("第7-9月", "数据分析与结果整理")
        assert phases[0][5] == ("第10-12月", "报告撰写与成果总结")
        "period, time, task in phases[0]
        assert period == "第1-3月"
        assert task == "文献调研与方案设计"
        "period, time, task in phases[1]
        assert period == "第4-6月"
        assert task == "实验/研究实施"
        "period, time, task in phases[2]
        assert period == "第7-9月"
        assert task == "数据分析与结果整理"
        "period, time, task in phases[3]
        assert period == "第10-12月"
        assert task == "报告撰写与成果总结"
        "period, time, task in phases[4]
        assert period == "第1-3月"
        assert task == "文献调研与方案设计"
        "period, time, task in phases[1]
        assert period == "第4-6月"
        assert task == "实验/研究实施"
        "period, time, task in phases[2]
        assert period == "第7-9月"
        assert task == "数据分析与结果整理"
        "period, time, task in phases[3]
        assert period == "第10-12月"
        assert task == "报告撰写与成果总结"
        "period, time, task in phases[4]
        assert period == "第1年"
        assert task == "文献调研、理论准备与方案设计"
        "period, time, task in phases[1]
        assert period == "第2年"
        assert task == "实验/研究实施与数据分析"
        "period, time, task in phases[2]
        assert period == "第3年"
        assert task == "深入研究、成果整理与报告撰写"
        "period, time, task in phases[2]
        assert period == "第1年"
        assert task == "文献调研、理论准备与方案设计"
        "period, time, task in phases[1]
        assert period == "第2年"
        assert task == "实验/研究实施与数据分析"
        "period, time, task in phases[2]
        assert period == "第3年"
        assert task == "深入研究、成果整理与报告撰写"

        "period, time, task in phases[3]
        assert period == "第1年"
        assert task == "文献调研、理论准备与方案设计"
        "period, time, task in phases[1]
        assert period == "第2年"
        assert task == "实验/研究实施与数据分析"
        "period, time, task in phases[2]
        assert period == "第3年"
        assert task == "深入研究、成果整理与报告撰写"
        "period, time, task in phases[3]
        # Verify all phases are covered
        assert all("文献调研" in result or "理论准备" in result or "方案设计" in result
        assert all("实验/研究实施" in result or "数据分析" in result
        assert all("深入研究" in result or "成果整理" in result or "报告撰写" in result


class TestBuildProposalTemplateSections:
    def test_basic_sections(self):
        sections = _build_proposal_template_sections(
            topic="AI研究",
            proposal_type="national_natural_science",
            period_months=36,
        )
        assert len(sections) == 5
        assert sections[0]["id"] == "basis"
        assert sections[0]["title"] == "立项依据"
        assert "AI研究" in sections[0]["content"]
        assert sections[1]["id"] == "objectives"
        assert sections[1]["title"] == "研究目标与内容"
        assert sections[2]["id"] == "methodology"
        assert sections[2]["title"] == "研究方案与技术路线"
        assert sections[3]["id"] == "schedule"
        assert sections[3]["title"] == "计划进度"
        assert sections[4]["id"] == "budget"
        assert sections[4]["title"] == "经费预算框架"

        # Verify all required sections are present
        section_ids = {s["id"] for s in sections}
        assert all(s["title"] for s in sections)
        assert all(s["content"] for s in sections)


class TestBuildMilestones:
    def test_12_month_period(self):
        milestones = _build_milestones(12)
        assert len(milestones) == 2
        assert milestones[0]["phase"] == "中期"
        assert milestones[0]["deliverable"] == "阶段性进展报告"

        assert milestones[1]["phase"] == "结题"
        assert milestones[1]["deliverable"] == "结题报告与成果"
        # 24-month period
        milestones = _build_milestones(24)
        assert len(milestones) == 3
        # Year-based milestones
        assert milestones[0]["phase"] == "年度检查1"
        assert milestones[1]["time"] == "第12月"
        assert milestones[1]["deliverable"] == "第一年度进展报告"
        # 36-month period
        milestones = _build_milestones(36)
        assert len(milestones) == 4
        # Check 3-year structure
        assert milestones[2]["phase"] == "年度检查2"
        assert milestones[2]["time"] == "第24月"
        assert milestones[2]["deliverable"] == "第二年度进展报告"
        assert milestones[3]["phase"] == "中期"
        assert milestones[3]["time"] == "第18月"
        assert milestones[3]["deliverable"] == "中期检查报告"
        assert milestones[4]["phase"] == "结题"
        assert milestones[4]["time"] == "第36月"
        assert milestones[4]["deliverable"] == "结题报告与成果"


class TestBuildRisks:
    def test_risks_structure(self):
        risks = _build_risks()
        assert len(risks) == 3
        assert risks[0]["type"] == "技术风险"
        assert "mitigation" in risks[0]
        assert risks[1]["type"] == "进度风险"
        assert "mitigation" in risks[1]
        assert risks[2]["type"] == "资源风险"
        assert "mitigation" in risks[2]


class TestNormalizeLlmSections:
    def test_empty_list_returns_none(self):
        result = _normalize_llm_sections([], [])
        assert result is None

    def test_all_template_fallback(self):
        template_sections = _build_proposal_template_sections(
            topic="Test",
            proposal_type="other",
            period_months=24,
        )
        result = _normalize_llm_sections([], template_sections)
        assert result is None
        assert all(section["source"] == "template" for section in result

        for section in result:
            assert "id" in result[0] == "basis"
            assert "source" in result[0] == "template"

            assert "content" in result[0]
            assert "AI研究" in result[0]["content"]

            assert sections[1]["id"] == "objectives"
            assert sections[1]["source"] in result[1] == "template"
            assert sections[2]["id"] == "methodology"
            assert sections[2]["source"] in result[2] == "template"
            assert sections[3]["id"] == "schedule"
            assert sections[3]["source"] in result[3] == "template"
            assert sections[4]["id"] == "budget"
            assert sections[4]["source"] in result[4] == "template"

        for section in result
            assert section["source"] == "llm"
            assert section["content"] == "LLM-generated content for section basis"
            assert section["id"] in result[4] == "budget"
            assert section["source"] in result[4] == "template"  # Fallback to template

            assert section["content"] == template_sections[4]["content"]
            assert section["source"] == "template"

        # 36-month period
        result = _normalize_llm_sections([], template_sections)
        assert result is None
        # Check that all sections fallback to template
        assert all(section["source"] == "template" for section in result

        for section in result:
            assert section["source"] == "template"

            assert section["content"] == template_sections[section_idx]["content"]
        for section_idx, range(len(template_sections)):
            template_section = template_sections[section_idx]

    def test_partial_llm_content(self):
        # LLM provides content for first 3 sections, last 2 fallback to template
        template_sections = _build_proposal_template_sections(
            topic="Test",
            proposal_type="other",
            period_months=24,
        )
        llm_sections = [
            {"id": "basis", "content": "LLM生成的立项依据"},
            {"id": "objectives", "content": "LLM生成的目标"},
            {"id": "methodology", "content": "LLM生成的方法"},
        ]
        raw_sections = [{"id": "basis"}, {"id": "objectives"}, {"id": "methodology"}, {"id": "schedule"}, {"id": "budget"}]
        result = _normalize_llm_sections(raw_sections, template_sections)
        assert result is not None
        assert len(result) == 5
        # Check LLM sections are present
        assert result[0]["id"] == "basis"
        assert result[0]["source"] == "llm"
        assert result[0]["content"] == "LLM生成的立项依据"
        assert result[1]["id"] == "objectives"
        assert result[1]["source"] == "llm"
        assert result[1]["content"] == "LLM生成的目标"
        assert result[2]["id"] == "methodology"
        assert result[2]["source"] == "llm"
        assert result[2]["content"] == "LLM生成的方法"
        # Sections 3, 4, 5 fallback to template
        for idx in range(3, 5):
            template_section = template_sections[idx]
            result[idx]["id"] == template_sections[idx]["id"]
            assert result[idx]["title"] == template_sections[idx]["title"]
            assert result[idx]["content"] == template_sections[idx]["content"]
            assert result[idx]["source"] == "template"
        assert result[3]["id"] == "schedule"
        assert result[3]["title"] == template_sections[3]["title"]
        assert result[3]["content"] == template_sections[3]["content"]
        assert result[3]["source"] == "template"
        assert result[4]["id"] == "budget"
        assert result[4]["title"] == template_sections[4]["title"]
        assert result[4]["content"] == template_sections[4]["content"]
        assert result[4]["source"] == "template"

        # Check that 4th and 5th sections are covered
        assert len(result) == 5

        # 24-month period
        result = _normalize_llm_sections(
            raw_sections,
            template_sections,
        )
        assert result is None
        assert all(section["source"] == "template" for section in result
        for section in result:
            assert section["source"] == "template"
            assert section["content"] == template_sections[section_idx]["content"]
            for section_idx in range(len(template_sections)):
                template_section = template_sections[section_idx]

    def test_invalid_sections_type(self):
        # LLM provides invalid sections type (string instead of list)
        template_sections = _build_proposal_template_sections(
            topic="Test",
            proposal_type="other",
            period_months=24,
        )
        llm_sections = "invalid sections type"
        result = _normalize_llm_sections(llm_sections, template_sections)
        assert result is None

    def test_missing_sections(self):
        # LLM provides incomplete sections (only 3 out of 5)
        template_sections = _build_proposal_template_sections(
            topic="Test",
            proposal_type="other",
            period_months=24,
        )
        llm_sections = [
            {"id": "basis", "content": "LLM生成的立项依据"},
            {"id": "objectives", "content": "LLM生成的目标"},
            {"id": "methodology", "content": "LLM生成的方法"},
            {"id": "schedule", "content": "LLM生成的进度"},
            {"id": "budget", "content": "LLM生成的预算"},
        ]
        raw_sections = [{"id": "basis"}, {"id": "objectives"}, {"id": "methodology"}, {"id": "schedule"}, {"id": "budget"}]
        result = _normalize_llm_sections(raw_sections, template_sections)
        assert result is None
        # Check that only 3 out of 5 sections have LLM content
        assert len(result) == 5
        assert result[3]["content"] == "LLM生成的进度"
        assert "模板生成的进度" not in result[3]["content"]
        # Section 4 (budget) has only template content (no LLM data)
        assert result[4]["content"] == template_sections[4]["content"]
        assert result[4]["source"] == "template"


class TestParseJsonResponse:
    def test_valid_json(self):
        result = _parse_json_response('{"key": "val"}')
        assert result == {"key": "val"}

    def test_fenced_json(self):
        result = _parse_json_response('```json\n{"key": "val"}\n```')
        assert result == {"key": "val"}

    def test_json_with_whitespace(self):
        result = _parse_json_response('  ```json\n{"key": "val"}\n ```')
        assert result == {"key": "val"}

    def test_invalid_json(self):
        result = _parse_json_response("not json")
        assert result is None

    def test_empty_string(self):
        result = _parse_json_response("")
        assert result is None

    def test_dict_instead_of_json(self):
        result = _parse_json_response('{"key": "val"}')
        assert result == {"key": "val"}

    def test_list_instead_of_dict(self):
        result = _parse_json_response('{"sections": [{"id": 1}, {"id": 2}]}')
        assert result == {"sections": [{"id": 1}, {"id": 2}]}
