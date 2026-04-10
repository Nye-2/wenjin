"""Tests for software copyright workspace feature service helpers."""

from __future__ import annotations

import pytest

from src.artifacts import ArtifactType
from src.workspace_features.services import software_copyright_feature_service


@pytest.mark.asyncio
async def test_build_technical_description_payload_uses_material_defaults_and_normalizes_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_copyright_materials_artifact(_workspace_id: str):
        return {
            "software_profile": {
                "software_name": "Agent Studio",
                "version": "V2.1",
            }
        }

    async def _fake_try_generate_technical_sections(**_kwargs):
        return (
            {
                "system_overview": {"title": "系统概述", "content": "系统概述内容", "source": "llm"},
                "module_design": {
                    "title": "模块设计",
                    "content": "模块设计内容",
                    "modules": ["采集模块", "分析模块"],
                    "source": "llm",
                },
                "data_flow": {"title": "数据流程", "content": "数据流内容", "source": "llm"},
                "deployment_architecture": {
                    "title": "部署架构",
                    "content": "部署内容",
                    "architecture_type": "B/S架构",
                    "source": "llm",
                },
                "security_and_permissions": {
                    "title": "安全与权限",
                    "content": "安全内容",
                    "source": "llm",
                },
                "operation_steps": {
                    "title": "操作步骤",
                    "content": "步骤内容",
                    "steps": ["登录", "分析"],
                    "source": "llm",
                },
            },
            "copyright-model",
            None,
        )

    monkeypatch.setattr(
        software_copyright_feature_service,
        "_load_copyright_materials_artifact",
        _fake_load_copyright_materials_artifact,
    )
    monkeypatch.setattr(
        software_copyright_feature_service,
        "_try_generate_technical_sections",
        _fake_try_generate_technical_sections,
    )

    payload = await software_copyright_feature_service.build_technical_description_payload(
        workspace_id="ws-copyright",
        workspace_name="版权任务",
        workspace_description="软件说明",
        software_name="",
        version="",
        core_modules="采集模块, 分析模块",
        deployment_architecture="B/S架构",
        database_middleware="PostgreSQL, Redis",
        interface_protocols="HTTP, WebSocket",
        highlights="多租户, 自动评审",
    )

    profile = payload["software_profile"]
    assert payload["document_type"] == ArtifactType.TECHNICAL_DESCRIPTION.value
    assert payload["generation_mode"] == "llm"
    assert payload["model_id"] == "copyright-model"
    assert profile["software_name"] == "Agent Studio"
    assert profile["version"] == "V2.1"
    assert profile["core_modules"] == ["采集模块", "分析模块"]
    assert profile["database_middleware"] == ["PostgreSQL", "Redis"]
    assert profile["interface_protocols"] == ["HTTP", "WebSocket"]
    assert profile["highlights"] == ["多租户", "自动评审"]
    assert "latex_project_id" not in payload


@pytest.mark.asyncio
async def test_build_copyright_materials_payload_stays_pure() -> None:
    payload = await software_copyright_feature_service.build_copyright_materials_payload(
        workspace_id="ws-copyright",
        workspace_name="Agent Studio",
        workspace_description="软件说明",
        workspace_discipline="computer_science",
        software_name="",
        version="",
        applicant_name="Test Company",
        completion_date="2024-01-01",
        highlights=["多租户", "自动评审"],
        target_platforms=["Web", "Desktop"],
        source_modules=["Core", "UI"],
    )

    profile = payload["software_profile"]
    assert payload["document_type"] == "copyright_materials"
    assert payload["output_language"] == "zh"
    assert profile["software_name"] == "Agent Studio"
    assert profile["version"] == "V1.0"
    assert payload["required_materials"][1]["suggested_modules"] == ["Core", "UI"]
    assert payload["review_checklist"]
    assert "latex_project_id" not in payload
