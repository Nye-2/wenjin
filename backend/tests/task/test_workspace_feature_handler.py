"""Tests for concrete workspace feature handlers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import (
    THESIS_HANDLER_KEYS,
    THESIS_AGENTS,
    THESIS_WORKSPACE_TYPES,
    _is_thesis_payload,
    execute_workspace_feature,
    execute_thesis_generation,
)


class TestThesisPayloadDetection:
    def test_all_thesis_sets_empty(self):
        """All thesis detection sets should be empty.
        thesis features now route via task_type at _dispatch_task level,
        so _is_thesis_payload() should never trigger."""
        assert THESIS_WORKSPACE_TYPES == set()
        assert THESIS_AGENTS == set()
        assert THESIS_HANDLER_KEYS == set()

    def test_is_thesis_payload_always_false(self):
        """_is_thesis_payload should return False for any workspace_feature payload.
        All thesis-specific features use task_type=thesis_generation and bypass
        execute_workspace_feature() entirely."""
        test_cases = [
            {"workspace_type": "thesis", "agent": "thesis_writer", "handler_key": "thesis.compile_export"},
            {"workspace_type": "thesis", "agent": "figure_planner", "handler_key": "thesis.figure_generation"},
            {"workspace_type": "thesis", "agent": "deep_research", "handler_key": "thesis.deep_research"},
            {"workspace_type": "thesis", "agent": "librarian", "handler_key": "thesis.literature_management"},
            {"workspace_type": "thesis", "agent": "scout", "handler_key": "thesis.opening_research"},
        ]
        for payload in test_cases:
            assert not _is_thesis_payload(payload), f"Should not detect thesis for {payload}"


class DummyArtifactService:
    """Record artifact creation calls for handler tests."""

    created_artifacts: list[dict] = []

    def __init__(self, db) -> None:
        self.db = db

    async def create(
        self,
        *,
        workspace_id: str,
        type: str,
        content: dict,
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
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


@pytest.mark.asyncio
async def test_copyright_materials_handler_persists_artifact(monkeypatch):
    """The software copyright materials feature should generate a real artifact."""
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

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "software_copyright",
        "workspace_name": "AcademiaGPT Desktop",
        "workspace_description": "Academic assistant desktop client",
        "workspace_discipline": "computer_science",
        "workspace_config": {"deployment": "desktop"},
        "feature_id": "copyright_materials",
        "feature_name": "材料准备",
        "agent": "writer",
        "agent_label": "Writer",
        "handler_key": "software_copyright.copyright_materials",
        "params": {
            "version": "V2.0",
            "applicant_name": "Open Research Lab",
            "source_modules": ["登录鉴权", "工作区管理", "成果导出"],
        },
    }

    result = await execute_workspace_feature(payload, progress)

    assert result["success"] is True
    assert result["refresh_targets"] == ["artifacts"]
    assert result["handler_key"] == "software_copyright.copyright_materials"
    assert result["artifacts"] == [
        {
            "id": "artifact-1",
            "type": "copyright_materials",
            "title": "AcademiaGPT Desktop 软著申请材料清单",
        }
    ]

    assert len(DummyArtifactService.created_artifacts) == 1
    artifact = DummyArtifactService.created_artifacts[0]
    assert artifact["workspace_id"] == "ws-1"
    assert artifact["type"] == "copyright_materials"
    assert artifact["title"] == "AcademiaGPT Desktop 软著申请材料清单"
    assert artifact["created_by_skill"] == "software_copyright.copyright_materials"
    assert artifact["content"]["document_type"] == "copyright_materials"
    assert artifact["content"]["software_profile"] == {
        "software_name": "AcademiaGPT Desktop",
        "version": "V2.0",
        "applicant_name": "Open Research Lab",
        "completion_date": "待确认开发完成日期",
        "description": "Academic assistant desktop client",
        "config_snapshot": {"deployment": "desktop"},
    }
    assert len(artifact["content"]["required_materials"]) == 5
    assert artifact["content"]["required_materials"][1]["suggested_modules"] == [
        "登录鉴权",
        "工作区管理",
        "成果导出",
    ]

    assert progress.update.await_count == 3


class TestThesisActionRouting:
    """Tests for thesis workflow action routing."""

    @pytest.mark.asyncio
    async def test_default_action_is_write_all(self):
        """Default action should call the full thesis workflow."""
        payload = {"workspace_id": "ws-1"}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.run_thesis_workflow_request") as mock_run:
            mock_run.return_value = {"status": "completed"}
            await execute_thesis_generation(payload, progress)
            # Default should call the thesis workflow (write_all behavior)
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_outline_action(self):
        """generate_outline action should route to outline-only handler."""
        payload = {"workspace_id": "ws-1", "action": "generate_outline", "params": {"topic": "test"}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.generate_outline_only") as mock_outline:
            mock_outline.return_value = {"message": "Outline generated"}
            result = await execute_thesis_generation(payload, progress)
            mock_outline.assert_called_once_with(payload, progress)
            assert result["message"] == "Outline generated"

    @pytest.mark.asyncio
    async def test_write_chapter_action(self):
        """write_chapter action should route to single chapter handler."""
        payload = {"workspace_id": "ws-1", "action": "write_chapter", "params": {"chapter_index": 1}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.write_single_chapter") as mock_ch:
            mock_ch.return_value = {"message": "Chapter written"}
            result = await execute_thesis_generation(payload, progress)
            mock_ch.assert_called_once_with(payload, progress)
            assert result["message"] == "Chapter written"
