"""Tests for the draft_intake_spec chat builtin."""

from __future__ import annotations

import pytest

from src.tools.builtins.draft_intake_spec import draft_intake_spec_tool


@pytest.mark.asyncio
async def test_draft_intake_spec_tool_returns_renderable_spec_payload() -> None:
    result = await draft_intake_spec_tool.ainvoke(
        {
            "workspace_type": "software_copyright",
            "capability_id": "software_copyright_application_pack",
            "title": "智慧排课系统软著申报 Spec",
            "status": "ready",
            "markdown": "# 智慧排课系统软著申报 Spec\n\n生成软著申报书、说明书、mock 后端代码和静态前端截图。",
            "params": {
                "software_name": "智慧排课系统",
                "target_platform": "web",
                "programming_language": "java",
                "visual_strategy": {
                    "ui_screenshots": "static_frontend_screenshot",
                },
            },
            "assumptions": ["未提供技术栈细节时按 Web 管理系统生成。"],
        },
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
    )

    assert result["status"] == "ready"
    spec = result["intake_spec"]
    assert spec["schema_version"] == "wenjin.intake_spec.v1"
    assert spec["workspace_id"] == "ws-1"
    assert spec["capability_id"] == "software_copyright_application_pack"
    assert spec["params"]["software_name"] == "智慧排课系统"
    assert spec["markdown"].startswith("# 智慧排课系统软著申报 Spec")


@pytest.mark.asyncio
async def test_draft_intake_spec_tool_returns_advisory_for_invalid_spec() -> None:
    result = await draft_intake_spec_tool.ainvoke(
        {
            "workspace_type": "math_modeling",
            "capability_id": "math_modeling_paper_pack",
            "title": "国赛论文 Spec",
            "status": "ready",
            "markdown": "# 国赛论文 Spec\n\n生成论文。",
            "params": {
                "problem_statement": "建立预测模型。",
                "programming_language": "matlab",
            },
        },
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
    )

    assert result["status"] == "advisory"
    assert result["code"] == "invalid_intake_spec"
    assert "programming_language" in result["detail"]
