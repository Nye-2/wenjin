"""End-to-end regression tests for thesis_writing LangGraph execution path."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.artifacts.types import ArtifactType
from src.task.handlers.workspace_feature_handler import execute_thesis_generation


class _FakeArtifactService:
    """Capture persisted artifacts without touching real DB."""

    created: list[dict] = []

    def __init__(self, _db) -> None:
        pass

    async def create(
        self,
        *,
        workspace_id: str,
        type: str,
        title: str,
        content: dict,
        created_by_skill: str,
    ) -> SimpleNamespace:
        self.__class__.created.append(
            {
                "workspace_id": workspace_id,
                "type": type,
                "title": title,
                "content": content,
                "created_by_skill": created_by_skill,
            }
        )
        idx = len(self.__class__.created)
        return SimpleNamespace(id=f"artifact-{idx}", type=type, title=title)


@asynccontextmanager
async def _fake_db_session():
    yield object()


@pytest.mark.asyncio
async def test_execute_thesis_writing_generate_outline_persists_outline_artifact():
    _FakeArtifactService.created.clear()

    payload = {
        "workspace_id": "ws-1",
        "workspace_name": "毕业论文",
        "workspace_type": "thesis",
        "feature_name": "论文写作",
        "handler_key": "thesis.thesis_writing",
        "params": {
            "action": "generate_outline",
            "paper_title": "测试论文",
            "target_words": 20000,
        },
    }
    langgraph_result = {
        "action": "generate_outline",
        "paper_title": "测试论文",
        "outline": {
            "abstract": "摘要",
            "keywords": ["研究方法"],
            "chapters": [
                {
                    "title": "绪论",
                    "position": "研究背景与意义",
                    "targetWords": 2400,
                    "keyPoints": ["问题定义"],
                    "sections": ["1.1 研究背景"],
                }
            ],
        },
        "source_context": {"literature_count": 12},
        "generation_mode": "template_fallback",
        "schema_version": "v1",
        "model_id": "deepseek-v3.2",
        "generated_at": "2026-03-18T00:00:00+00:00",
    }

    progress = AsyncMock()

    with (
        patch(
            "src.agents.workspace_lead_agent.execute_feature_graph",
            new=AsyncMock(return_value=langgraph_result),
        ),
        patch(
            "src.task.handlers.workspace_feature_handler.ArtifactService",
            _FakeArtifactService,
        ),
        patch(
            "src.task.handlers.workspace_feature_handler.get_db_session",
            _fake_db_session,
        ),
        patch("src.task.handlers.workspace_feature_handler._schedule_memory_extraction"),
    ):
        result = await execute_thesis_generation(payload, progress)

    assert result["success"] is True
    assert result["data"]["action"] == "generate_outline"
    assert result["artifacts"]
    assert result["artifacts"][0]["type"] == ArtifactType.FRAMEWORK_OUTLINE.value

    assert len(_FakeArtifactService.created) == 1
    persisted = _FakeArtifactService.created[0]
    assert persisted["type"] == ArtifactType.FRAMEWORK_OUTLINE.value
    assert persisted["content"]["paper_title"] == "测试论文"
    assert persisted["content"]["outline"]["chapters"][0]["title"] == "绪论"


@pytest.mark.asyncio
async def test_execute_thesis_writing_write_chapter_persists_chapter_artifact():
    _FakeArtifactService.created.clear()

    payload = {
        "workspace_id": "ws-1",
        "workspace_name": "毕业论文",
        "workspace_type": "thesis",
        "feature_name": "论文写作",
        "handler_key": "thesis.thesis_writing",
        "params": {
            "action": "write_chapter",
            "paper_title": "测试论文",
            "chapter_index": 0,
            "chapter_title": "绪论",
            "target_words": 2500,
        },
    }
    langgraph_result = {
        "action": "write_chapter",
        "paper_title": "测试论文",
        "chapter": {
            "paper_title": "测试论文",
            "chapter_index": 0,
            "chapter_title": "绪论",
            "target_words": 2500,
            "estimated_words": 900,
            "markdown": "# 绪论\\n\\n正文内容。",
            "references_used": ["ref-1"],
            "schema_version": "v1",
        },
        "generation_mode": "template_fallback",
        "schema_version": "v1",
        "model_id": "deepseek-v3.2",
        "generated_at": "2026-03-18T00:00:00+00:00",
    }

    progress = AsyncMock()

    with (
        patch(
            "src.agents.workspace_lead_agent.execute_feature_graph",
            new=AsyncMock(return_value=langgraph_result),
        ),
        patch(
            "src.task.handlers.workspace_feature_handler.ArtifactService",
            _FakeArtifactService,
        ),
        patch(
            "src.task.handlers.workspace_feature_handler.get_db_session",
            _fake_db_session,
        ),
        patch("src.task.handlers.workspace_feature_handler._schedule_memory_extraction"),
    ):
        result = await execute_thesis_generation(payload, progress)

    assert result["success"] is True
    assert result["data"]["action"] == "write_chapter"
    assert result["artifacts"]
    assert result["artifacts"][0]["type"] == ArtifactType.THESIS_CHAPTER.value

    assert len(_FakeArtifactService.created) == 1
    persisted = _FakeArtifactService.created[0]
    assert persisted["type"] == ArtifactType.THESIS_CHAPTER.value
    assert persisted["content"]["chapter_title"] == "绪论"
    assert persisted["content"]["model_id"] == "deepseek-v3.2"
