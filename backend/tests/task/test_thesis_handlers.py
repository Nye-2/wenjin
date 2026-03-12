"""Tests for thesis workspace feature handlers (figure_generation, compile_export, opening_research)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature


class DummyArtifactService:
    created_artifacts: list[dict] = []

    def __init__(self, db) -> None:
        self.db = db

    async def create(self, *, workspace_id, type, content, title=None,
                     created_by_skill=None, parent_artifact_id=None):
        record = {"workspace_id": workspace_id, "type": type, "content": content,
                  "title": title, "created_by_skill": created_by_skill}
        self.created_artifacts.append(record)
        return SimpleNamespace(id=f"artifact-{len(self.created_artifacts)}", type=type, title=title)


@pytest.fixture(autouse=True)
def mock_runtime(monkeypatch):
    DummyArtifactService.created_artifacts = []

    @asynccontextmanager
    async def fake_get_db_session():
        yield object()

    monkeypatch.setattr("src.workspace_features.runtime.get_db_session", fake_get_db_session)
    monkeypatch.setattr("src.workspace_features.runtime.ArtifactService", DummyArtifactService)


@pytest.mark.asyncio
async def test_figure_generation_handler():
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


@pytest.mark.asyncio
async def test_compile_export_handler():
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


@pytest.mark.asyncio
async def test_opening_research_handler():
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
