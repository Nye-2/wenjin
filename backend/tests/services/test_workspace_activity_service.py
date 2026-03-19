"""Tests for workspace activity aggregation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.workspace_activity_service import WorkspaceActivityService


@pytest.mark.asyncio
async def test_get_activity_merges_sources_and_sorts_descending():
    db = AsyncMock()
    service = WorkspaceActivityService(db)

    now = datetime.now(UTC)
    service._get_recent_threads = AsyncMock(return_value=[])
    service._get_task_activity = AsyncMock(
        return_value=[
            {
                "id": "task:1",
                "kind": "feature_task",
                "workspace_id": "ws-1",
                "occurred_at": now - timedelta(minutes=3),
                "title": "Task",
                "summary": None,
                "status": "running",
                "thread_id": None,
                "task_id": "1",
                "artifact_id": None,
                "feature_id": "deep_research",
                "subagent_type": None,
                "metadata": {},
            }
        ]
    )
    service._build_chat_activity = MagicMock(
        return_value=[
            {
                "id": "chat:1",
                "kind": "chat_thread",
                "workspace_id": "ws-1",
                "occurred_at": now,
                "title": "Chat",
                "summary": "latest reply",
                "status": None,
                "thread_id": "thread-1",
                "task_id": None,
                "artifact_id": None,
                "feature_id": None,
                "subagent_type": None,
                "metadata": {},
            }
        ]
    )
    service._get_artifact_activity = AsyncMock(
        return_value=[
            {
                "id": "artifact:1",
                "kind": "artifact",
                "workspace_id": "ws-1",
                "occurred_at": now - timedelta(minutes=1),
                "title": "Artifact",
                "summary": "draft",
                "status": "draft",
                "thread_id": None,
                "task_id": None,
                "artifact_id": "artifact-1",
                "feature_id": None,
                "subagent_type": None,
                "metadata": {},
            }
        ]
    )
    service._get_subagent_activity = AsyncMock(return_value=[])

    result = await service.get_activity("ws-1", user_id="user-1", limit=10)

    assert [item["kind"] for item in result["items"]] == [
        "chat_thread",
        "artifact",
        "feature_task",
    ]
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_build_chat_activity_uses_latest_message_preview_and_skill():
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        title="Literature review thread",
        skill="deep-research",
        updated_at=datetime.now(UTC),
        messages=[
            {"role": "user", "content": "Please review these papers."},
            {"role": "assistant", "content": "I found three themes across the literature."},
        ],
    )

    items = service._build_chat_activity([thread])

    assert len(items) == 1
    assert items[0]["title"] == "Literature review thread"
    assert items[0]["summary"] == "I found three themes across the literature."
    assert items[0]["metadata"]["skill"] == "deep-research"
