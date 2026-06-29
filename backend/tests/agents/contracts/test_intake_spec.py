"""Contracts for chat-authored super-workflow intake specs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.contracts.intake_spec import IntakeSpecV1


def test_math_modeling_intake_spec_defaults_to_python() -> None:
    spec = IntakeSpecV1(
        spec_id="spec-mm-1",
        workspace_id="ws-1",
        workspace_type="math_modeling",
        capability_id="math_modeling_paper_pack",
        title="国赛 C 题论文生成 Spec",
        status="ready",
        markdown="# 国赛 C 题论文生成 Spec\n\n目标：完成论文与图表。",
        params={
            "problem_statement": "请根据题目数据建立预测模型。",
        },
    )

    assert spec.params["programming_language"] == "python"


def test_math_modeling_intake_spec_rejects_non_python_language() -> None:
    with pytest.raises(ValidationError, match="programming_language"):
        IntakeSpecV1(
            spec_id="spec-mm-2",
            workspace_id="ws-1",
            workspace_type="math_modeling",
            capability_id="math_modeling_paper_pack",
            title="国赛论文生成 Spec",
            status="ready",
            markdown="# Spec\n\n目标：完成论文。",
            params={
                "problem_statement": "请根据题目数据建立预测模型。",
                "programming_language": "matlab",
            },
        )


def test_software_copyright_intake_spec_rejects_ai_generated_ui_evidence() -> None:
    with pytest.raises(ValidationError, match="ui_screenshots"):
        IntakeSpecV1(
            spec_id="spec-sc-1",
            workspace_id="ws-1",
            workspace_type="software_copyright",
            capability_id="software_copyright_application_pack",
            title="智慧排课系统软著 Spec",
            status="ready",
            markdown="# 智慧排课系统软著 Spec\n\n目标：生成申报材料包。",
            params={
                "software_name": "智慧排课系统",
                "target_platform": "web",
                "visual_strategy": {
                    "ui_screenshots": "gpt-image2",
                },
            },
        )


def test_software_copyright_intake_spec_rejects_ai_generated_visual_strategy_anywhere() -> None:
    with pytest.raises(ValidationError, match="AI-generated UI evidence"):
        IntakeSpecV1(
            spec_id="spec-sc-2",
            workspace_id="ws-1",
            workspace_type="software_copyright",
            capability_id="software_copyright_application_pack",
            title="智慧排课系统软著 Spec",
            status="ready",
            markdown="# 智慧排课系统软著 Spec\n\n目标：生成申报材料包。",
            params={
                "software_name": "智慧排课系统",
                "visual_strategy": {
                    "mock_backend": "java",
                    "screenshots": {
                        "mode": "gpt-image2",
                    },
                },
            },
        )


def test_intake_spec_rejects_wrong_workspace_capability_pair() -> None:
    with pytest.raises(ValidationError, match="capability_id"):
        IntakeSpecV1(
            spec_id="spec-bad-1",
            workspace_id="ws-1",
            workspace_type="software_copyright",
            capability_id="math_modeling_paper_pack",
            title="错误匹配 Spec",
            status="ready",
            markdown="# Spec\n\n目标：生成材料。",
            params={"software_name": "智慧排课系统"},
        )
