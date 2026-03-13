"""Tests for thesis workspace feature handlers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature


class DummyArtifactService:
    created_artifacts: list[dict] = []

    def __init__(self, db) -> None:
        self.db = db

    async def create(
        self,
        *,
        workspace_id,
        type,
        content,
        title=None,
        created_by_skill=None,
        parent_artifact_id=None,
    ):
        record = {
            "workspace_id": workspace_id,
            "type": type,
            "content": content,
            "title": title,
            "created_by_skill": created_by_skill,
            "parent_artifact_id": parent_artifact_id,
        }
        self.created_artifacts.append(record)
        return SimpleNamespace(
            id=f"artifact-{len(self.created_artifacts)}",
            type=type,
            title=title,
        )


@pytest.fixture(autouse=True)
def mock_runtime(monkeypatch):
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr(
        "src.workspace_features.runtime.get_db_session",
        fake_get_db_session,
    )
    monkeypatch.setattr(
        "src.workspace_features.runtime.ArtifactService",
        DummyArtifactService,
    )


@pytest.mark.asyncio
async def test_figure_generation_handler(monkeypatch):
    monkeypatch.setattr(
        "src.workspace_features.handlers.thesis.build_figure_payload",
        AsyncMock(
            return_value={
                "figure_type": "flowchart",
                "description": "系统架构流程图",
                "chapter_index": 2,
                "strategy": "mermaid",
                "status": "degraded",
                "source_code": "flowchart TD; A-->B",
                "upgrade": {
                    "auto_upgrade": True,
                    "required_execution_type": "mermaid_diagram",
                    "provider_ready": False,
                    "last_error": "provider unavailable",
                },
            }
        ),
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "My Thesis",
        "feature_id": "figure_generation",
        "feature_name": "图表生成",
        "agent": "figure_planner",
        "handler_key": "thesis.figure_generation",
        "params": {
            "description": "系统架构流程图",
            "type": "flowchart",
            "chapter_index": 2,
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "thesis.figure_generation"
    assert result["data"]["generation_status"] == "degraded"

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "figure"
    assert artifact["content"]["status"] == "degraded"
    assert artifact["content"]["strategy"] == "mermaid"
    assert artifact["content"]["upgrade"]["auto_upgrade"] is True
    assert artifact["content"]["source_code"]


@pytest.mark.asyncio
async def test_literature_management_handler_persists_inventory_artifact(monkeypatch):
    monkeypatch.setattr(
        "src.workspace_features.handlers.thesis.build_literature_management_payload",
        AsyncMock(
            return_value={
                "workspace_id": "ws-1",
                "workspace_name": "My Thesis",
                "summary": {
                    "total": 12,
                    "core_count": 5,
                },
                "recommended_actions": ["继续补充近三年高相关文献"],
            }
        ),
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "My Thesis",
        "feature_id": "literature_management",
        "feature_name": "文献管理",
        "agent": "librarian",
        "handler_key": "thesis.literature_management",
        "params": {
            "topic": "深度学习",
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "thesis.literature_management"
    assert result["data"]["total"] == 12
    assert result["data"]["core_count"] == 5

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "literature_inventory"
    assert artifact["content"]["summary"]["total"] == 12
    assert artifact["content"]["summary"]["core_count"] == 5


@pytest.mark.asyncio
async def test_compile_export_handler(monkeypatch):
    monkeypatch.setattr(
        "src.workspace_features.handlers.thesis.build_compile_payload",
        AsyncMock(
            return_value={
                "template": "default",
                "compiler": "xelatex",
                "bibliography_style": "gbt7714",
                "latex_content": (
                    "\\documentclass{ctexart}\\begin{document}Test\\end{document}"
                ),
                "bib_content": "",
                "compile_status": "failed",
                "pdf_path": None,
                "compile_error": "Unsupported command",
                "source_summary": {
                    "outline_count": 1,
                    "chapter_count": 2,
                    "figure_count": 0,
                    "literature_count": 3,
                },
            }
        ),
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "My Thesis",
        "feature_id": "compile_export",
        "feature_name": "编译导出",
        "agent": "thesis_writer",
        "handler_key": "thesis.compile_export",
        "params": {
            "template": "default",
            "compiler": "xelatex",
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "thesis.compile_export"
    assert result["data"]["compile_status"] == "failed"

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "paper_draft"
    assert artifact["content"]["compile_status"] == "failed"
    assert artifact["content"]["latex_content"].startswith("\\documentclass")
    assert artifact["content"]["source_summary"]["chapter_count"] == 2


@pytest.mark.asyncio
async def test_opening_research_handler(monkeypatch):
    monkeypatch.setattr(
        "src.workspace_features.handlers.thesis.build_opening_report_payload",
        AsyncMock(
            return_value={
                "topic": "基于深度学习的图像分割",
                "report_type": "opening_report",
                "generation_mode": "template_fallback",
                "generation_error": "no_generation_model_configured",
                "sections": [
                    {
                        "title": "研究背景与意义",
                        "content": "阐述问题背景与研究意义。",
                        "source": "template",
                    },
                    {
                        "title": "研究目标与主要内容",
                        "content": "定义研究目标与核心问题。",
                        "source": "template",
                    },
                ],
            }
        ),
    )

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "My Thesis",
        "workspace_description": "基于深度学习的图像分割研究",
        "feature_id": "opening_research",
        "feature_name": "开题调研",
        "agent": "scout",
        "handler_key": "thesis.opening_research",
        "params": {
            "topic": "基于深度学习的图像分割",
            "report_type": "opening_report",
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "thesis.opening_research"
    assert result["data"]["generation_mode"] == "template_fallback"

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["type"] == "opening_report"
    assert artifact["content"]["generation_mode"] == "template_fallback"
    assert len(artifact["content"]["sections"]) >= 2
    assert artifact["content"]["sections"][0]["source"] == "template"
