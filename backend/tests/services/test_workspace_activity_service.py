"""Tests for workspace activity aggregation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.workspace_activity_contracts import (
    build_subagent_activity_item,
    build_task_activity_item,
    build_thread_activity_item,
    serialize_activity_item,
)
from src.services.workspace_activity_service import WorkspaceActivityService


@pytest.mark.asyncio
async def test_get_activity_merges_sources_and_sorts_descending(
    monkeypatch: pytest.MonkeyPatch,
):
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    monkeypatch.setattr(
        "src.services.workspace_activity_service.get_workspace_type",
        AsyncMock(return_value="thesis"),
    )

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
    service._build_thread_activity = MagicMock(
        return_value=[
            {
                "id": "thread:1",
                "kind": "thread",
                "workspace_id": "ws-1",
                "occurred_at": now,
                "title": "Thread",
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
        "thread",
        "artifact",
        "feature_task",
    ]
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_build_thread_activity_uses_latest_message_preview_and_skill():
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

    items = service._build_thread_activity([thread], workspace_type="thesis")

    assert len(items) == 1
    assert items[0]["title"] == "Literature review thread"
    assert items[0]["summary"] == "I found three themes across the literature."
    assert items[0]["skill"] == "deep-research"
    assert items[0]["skill_name"] is None
    assert items[0]["metadata"]["skill"] == "deep-research"
    assert items[0]["metadata"]["skill_name"] is None


@pytest.mark.asyncio
async def test_build_thread_activity_includes_token_usage_metadata():
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    thread = SimpleNamespace(
        id="thread-usage",
        workspace_id="ws-1",
        title="Usage thread",
        skill="deep-research",
        updated_at=datetime.now(UTC),
        messages=[
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "latest response",
                "metadata": {
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "total_tokens": 16,
                    }
                },
            },
        ],
    )

    items = service._build_thread_activity([thread], workspace_type="thesis")

    assert len(items) == 1
    assert items[0]["metadata"]["last_message_token_usage"]["total_tokens"] == 16
    assert items[0]["metadata"]["thread_token_usage"]["total_tokens"] == 16


def test_build_thread_activity_item_uses_canonical_thread_shape() -> None:
    item = build_thread_activity_item(
        thread_id="thread-1",
        workspace_id="ws-1",
        title=None,
        skill="peer-reviewer",
        skill_name="同行评审",
        message_count=3,
        last_message_preview=None,
        last_message_role="assistant",
        occurred_at="2026-03-25T00:00:00Z",
    )

    assert item == {
        "id": "thread:thread-1",
        "kind": "thread",
        "workspace_id": "ws-1",
        "occurred_at": "2026-03-25T00:00:00Z",
        "title": "Thread session",
        "summary": "3 messages",
        "status": None,
        "thread_id": "thread-1",
        "task_id": None,
        "artifact_id": None,
        "feature_id": None,
        "skill": "peer-reviewer",
        "skill_name": "同行评审",
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": None,
        "metadata": {
            "skill": "peer-reviewer",
            "skill_name": "同行评审",
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


def test_task_activity_promotes_result_artifact_as_retry_seed() -> None:
    item = build_task_activity_item(
        task_id="task-artifact",
        workspace_id="ws-1",
        task_type="workspace_feature",
        payload={
            "feature_id": "framework_outline",
            "thread_id": "thread-1",
            "params": {"topic": "LLM planning"},
        },
        status="success",
        progress=100,
        message="done",
        error=None,
        result={
            "artifact_ids": ["artifact-current"],
            "artifacts": [{"id": "artifact-current", "title": "LLM Framework"}],
        },
        occurred_at="2026-03-25T00:00:00Z",
        completed_at="2026-03-25T00:00:00Z",
    )

    assert item["artifact_id"] == "artifact-current"
    assert item["metadata"]["params"]["source_artifact_id"] == "artifact-current"
    assert item["metadata"]["params"]["context_artifact_ids"] == ["artifact-current"]
    assert item["metadata"]["result_artifact_ids"] == ["artifact-current"]
    assert item["metadata"]["next_actions"] == [
        {
            "action": "open_artifact",
            "label": "查看产物",
            "artifact_id": "artifact-current",
            "title": "LLM Framework",
        },
        {
            "action": "rerun_from_artifact",
            "label": "基于当前产物继续",
            "feature_id": "framework_outline",
            "topic": "LLM planning",
            "source_artifact_id": "artifact-current",
            "context_artifact_ids": ["artifact-current"],
        },
    ]


def test_task_activity_derives_prism_review_action_for_pending_file_changes() -> None:
    item = build_task_activity_item(
        task_id="task-prism",
        workspace_id="ws-1",
        task_type="workspace_feature",
        payload={
            "feature_id": "thesis_writing",
            "thread_id": "thread-1",
            "params": {"topic": "chapter 1"},
        },
        status="success",
        progress=100,
        message="done",
        error=None,
        result={
            "data": {
                "latex_project_id": "latex-1",
                "file_changes": [
                    {
                        "logical_key": "section:introduction",
                        "path": "sections/introduction.tex",
                    }
                ],
            }
        },
        occurred_at="2026-03-25T00:00:00Z",
        completed_at="2026-03-25T00:00:00Z",
    )

    assert {
        (action.get("action"), action.get("label"), action.get("project_id"))
        for action in item["metadata"]["next_actions"]
    } >= {
        ("preview_prism_changes", "预览待确认修改", "latex-1"),
    }


def test_task_record_to_activity_includes_token_usage_metadata() -> None:
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    record = SimpleNamespace(
        id="task-usage",
        task_type="workspace_feature",
        payload={"feature_id": "deep_research", "params": {"topic": "LLM"}},
        status="completed",
        progress=100,
        message="done",
        error=None,
        result={"summary": "ok"},
        created_at=datetime(2026, 4, 13, tzinfo=UTC),
        started_at=datetime(2026, 4, 13, 0, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 13, 0, 2, tzinfo=UTC),
    )

    item = service._task_record_to_activity(
        record,
        "ws-1",
        token_usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        subagent_count=3,
    )

    assert item["metadata"]["token_usage"]["total_tokens"] == 150
    assert item["metadata"]["subagent_count"] == 3


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
        "skill": None,
        "skill_name": None,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": "paper_critic",
        "metadata": {
            "prompt": "Review the paper",
            "output_preview": "Found three issues",
            "error": None,
        },
    }


def test_subagent_record_to_activity_includes_token_usage_metadata() -> None:
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    now = datetime.now(UTC)
    record = SimpleNamespace(
        id="sub-usage",
        workspace_id="ws-1",
        thread_id="thread-1",
        status="completed",
        subagent_type="scout",
        prompt="Find papers",
        output_preview="Found 5 papers",
        error=None,
        task_metadata={
            "token_usage": {
                "input_tokens": 80,
                "output_tokens": 20,
                "total_tokens": 100,
            },
            "model_name": "gpt-4.1-mini",
        },
        created_at=now,
        updated_at=now,
        completed_at=now,
    )

    item = service._subagent_record_to_activity(record)

    assert item["metadata"]["token_usage"]["total_tokens"] == 100
    assert item["metadata"]["model_name"] == "gpt-4.1-mini"


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


def test_artifact_activity_uses_canonical_creator_skill_name() -> None:
    db = AsyncMock()
    service = WorkspaceActivityService(db)
    artifact = SimpleNamespace(
        id="artifact-1",
        workspace_id="ws-1",
        type="figure",
        title="图表草稿",
        created_by_skill="figure-designer",
        status="draft",
        created_at=datetime(2026, 3, 25, tzinfo=UTC),
    )

    item = service._artifact_to_activity(artifact, workspace_type="thesis")

    assert item["created_by_skill"] == "figure-designer"
    assert item["created_by_skill_name"] is None
    assert item["metadata"]["created_by_skill_name"] is None
    # Summary falls back to the raw created_by_skill id when no display name is available.
    assert item["summary"] == "figure-designer"


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
            "skill": None,
            "skill_name": None,
            "created_by_skill": None,
            "created_by_skill_name": None,
            "subagent_type": "paper_critic",
            "metadata": {
                "prompt": "Review this paper",
                "output_preview": "Found three issues",
                "error": None,
            },
        }
    ]
