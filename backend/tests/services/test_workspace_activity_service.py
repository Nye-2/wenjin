"""Tests for workspace activity aggregation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.workspace_activity_contracts import (
    build_chat_activity_item,
    build_subagent_activity_item,
    build_task_activity_item,
    serialize_activity_item,
)
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


def test_build_chat_activity_item_uses_canonical_chat_shape() -> None:
    item = build_chat_activity_item(
        thread_id="thread-1",
        workspace_id="ws-1",
        title=None,
        skill="peer-reviewer",
        message_count=3,
        last_message_preview=None,
        last_message_role="assistant",
        occurred_at="2026-03-25T00:00:00Z",
    )

    assert item == {
        "id": "chat:thread-1",
        "kind": "chat_thread",
        "workspace_id": "ws-1",
        "occurred_at": "2026-03-25T00:00:00Z",
        "title": "Chat session",
        "summary": "3 messages",
        "status": None,
        "thread_id": "thread-1",
        "task_id": None,
        "artifact_id": None,
        "feature_id": None,
        "subagent_type": None,
        "metadata": {
            "skill": "peer-reviewer",
            "message_count": 3,
            "last_message_role": "assistant",
        },
    }


def test_build_task_activity_item_uses_canonical_task_shape() -> None:
    item = build_task_activity_item(
        task_id="task-1",
        workspace_id="ws-1",
        task_type="workspace_feature",
        payload={
            "feature_id": "framework_outline",
            "thread_id": "thread-1",
            "params": {"topic": "LLM planning", "action": "generate_outline"},
        },
        status="pending",
        progress=0,
        message=None,
        error=None,
        occurred_at="2026-03-25T00:00:00Z",
        created_at="2026-03-25T00:00:00Z",
    )

    assert item["id"] == "task:task-1"
    assert item["title"] == "Framework Outline"
    assert item["summary"] == "LLM planning"
    assert item["thread_id"] == "thread-1"
    assert item["metadata"]["action"] == "generate_outline"


def test_build_subagent_activity_item_uses_canonical_subagent_shape() -> None:
    item = build_subagent_activity_item(
        workspace_id="ws-1",
        task_id="sub-1",
        thread_id="thread-1",
        status="completed",
        subagent_type="paper_critic",
        prompt="Review the paper",
        output_preview="Found three issues",
        error=None,
        occurred_at="2026-03-25T00:00:00Z",
    )

    assert item == {
        "id": "subagent:sub-1",
        "kind": "subagent_task",
        "workspace_id": "ws-1",
        "occurred_at": "2026-03-25T00:00:00Z",
        "title": "Paper Critic",
        "summary": "Found three issues",
        "status": "completed",
        "thread_id": "thread-1",
        "task_id": "sub-1",
        "artifact_id": None,
        "feature_id": None,
        "subagent_type": "paper_critic",
        "metadata": {
            "prompt": "Review the paper",
            "output_preview": "Found three issues",
            "error": None,
        },
    }


def test_serialize_activity_item_normalizes_datetime_fields() -> None:
    item = serialize_activity_item(
        {
            "id": "task:1",
            "kind": "feature_task",
            "workspace_id": "ws-1",
            "occurred_at": datetime(2026, 3, 25, tzinfo=UTC),
            "title": "Task",
            "summary": "Running",
            "status": "running",
            "thread_id": "thread-1",
            "task_id": "1",
            "artifact_id": None,
            "feature_id": "deep_research",
            "subagent_type": None,
            "metadata": {"created_at": "2026-03-25T00:00:00+00:00"},
        }
    )

    assert item["occurred_at"] == "2026-03-25T00:00:00+00:00"


@pytest.mark.asyncio
async def test_get_subagent_activity_reads_persisted_records() -> None:
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    now = datetime.now(UTC)
    created_at = now - timedelta(minutes=5)
    record = SimpleNamespace(
        id="sub-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        status="completed",
        subagent_type="paper_critic",
        prompt="Review this paper",
        output_preview="Found three issues",
        error=None,
        created_at=created_at,
        updated_at=now - timedelta(minutes=1),
        completed_at=now,
    )
    db.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[record])))
    )

    items = await service._get_subagent_activity("ws-1", limit=10)

    assert items == [
        {
            "id": "subagent:sub-1",
            "kind": "subagent_task",
            "workspace_id": "ws-1",
            "occurred_at": now,
            "title": "Paper Critic",
            "summary": "Found three issues",
            "status": "completed",
            "thread_id": "thread-1",
            "task_id": "sub-1",
            "artifact_id": None,
            "feature_id": None,
            "subagent_type": "paper_critic",
            "metadata": {
                "prompt": "Review this paper",
                "output_preview": "Found three issues",
                "error": None,
            },
        }
    ]
