"""Tests for workspace activity aggregation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice.domains.asset.contracts import WorkspaceAssetProjection
from src.dataservice.domains.execution.contracts import (
    ExecutionNodeProjection,
    ExecutionRecordProjection,
)
from src.dataservice.domains.review.contracts import ReviewItemProjection
from src.services.workspace_activity_contracts import (
    build_prism_review_activity_item,
    build_subagent_activity_item,
    build_task_activity_item,
    build_thread_activity_item,
    serialize_activity_item,
)
from src.services.workspace_activity_service import WorkspaceActivityService


def _execution_projection(**overrides) -> ExecutionRecordProjection:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionRecordProjection(
        id=overrides.get("id", "exec-1"),
        user_id=overrides.get("user_id", "user-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        thread_id=overrides.get("thread_id", "thread-1"),
        execution_type=overrides.get("execution_type", "workspace_feature"),
        capability_id=overrides.get("capability_id", "deep_research"),
        entry_skill_id=overrides.get("entry_skill_id"),
        workspace_type=overrides.get("workspace_type", "thesis"),
        display_name=overrides.get("display_name"),
        status=overrides.get("status", "completed"),
        task_brief_json=overrides.get("task_brief_json", {"topic": "LLM"}),
        result_json=overrides.get("result_json", {"summary": "ok"}),
        error_text=overrides.get("error_text"),
        result_summary=overrides.get("result_summary"),
        graph_json=overrides.get("graph_json"),
        node_states_json=overrides.get("node_states_json", {}),
        runtime_state_json=overrides.get("runtime_state_json"),
        progress=overrides.get("progress", 100),
        message=overrides.get("message", "done"),
        artifact_ids=overrides.get("artifact_ids", []),
        next_actions=overrides.get("next_actions", []),
        advisory_code=overrides.get("advisory_code"),
        last_error=overrides.get("last_error"),
        parent_execution_id=overrides.get("parent_execution_id"),
        child_execution_ids=overrides.get("child_execution_ids", []),
        dispatch_mode=overrides.get("dispatch_mode"),
        worker_task_id=overrides.get("worker_task_id"),
        created_at=now,
        started_at=overrides.get("started_at"),
        completed_at=overrides.get("completed_at"),
        updated_at=overrides.get("updated_at", now),
    )


def _node_projection(**overrides) -> ExecutionNodeProjection:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionNodeProjection(
        id=overrides.get("id", "node-1"),
        execution_id=overrides.get("execution_id", "exec-1"),
        parent_node_id=overrides.get("parent_node_id"),
        node_id=overrides.get("node_id", "phase__task"),
        node_type=overrides.get("node_type", "paper_critic"),
        label=overrides.get("label", "Paper Critic"),
        status=overrides.get("status", "completed"),
        input_data=overrides.get("input_data"),
        output_data=overrides.get("output_data"),
        thinking=overrides.get("thinking"),
        tool_calls=overrides.get("tool_calls"),
        token_usage=overrides.get("token_usage"),
        node_metadata=overrides.get("node_metadata"),
        started_at=overrides.get("started_at"),
        completed_at=overrides.get("completed_at"),
        created_at=now,
        updated_at=overrides.get("updated_at", now),
    )


def _asset_projection(**overrides) -> WorkspaceAssetProjection:
    now = overrides.get("created_at") or datetime.now(UTC)
    return WorkspaceAssetProjection(
        id=overrides.get("id", "asset-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        asset_kind=overrides.get("asset_kind", "figure"),
        name=overrides.get("name", "Figure Draft"),
        title=overrides.get("title", "图表草稿"),
        mime_type=overrides.get("mime_type", "image/png"),
        storage_backend=overrides.get("storage_backend", "local"),
        storage_path=overrides.get("storage_path", "/tmp/figure.png"),
        size_bytes=overrides.get("size_bytes"),
        content_hash=overrides.get("content_hash"),
        parent_asset_id=overrides.get("parent_asset_id"),
        created_by=overrides.get("created_by", "figure-designer"),
        source_kind=overrides.get("source_kind", "artifacts"),
        source_id=overrides.get("source_id", "artifact-1"),
        metadata_json=overrides.get("metadata_json", {"status": "draft", "version": 2}),
        deleted_at=overrides.get("deleted_at"),
        created_at=now,
        updated_at=overrides.get("updated_at", now),
    )


class FakeActivityDataServiceClient:
    def __init__(self) -> None:
        self.list_workspace_conversation_thread_summaries = AsyncMock(return_value=[])
        self.list_conversation_messages = AsyncMock(return_value=[])
        self.list_review_items = AsyncMock(return_value=[])
        self.list_assets = AsyncMock(return_value=[])
        self.list_executions = AsyncMock(return_value=[])
        self.list_execution_nodes_by_execution_ids = AsyncMock(return_value=[])


@pytest.mark.asyncio
async def test_get_activity_merges_sources_and_sorts_descending(
    monkeypatch: pytest.MonkeyPatch,
):
    service = WorkspaceActivityService()
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
    service._build_thread_activity = AsyncMock(
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
    service._get_prism_review_activity = AsyncMock(return_value=[])

    result = await service.get_activity("ws-1", user_id="user-1", limit=10)

    assert [item["kind"] for item in result["items"]] == [
        "thread",
        "artifact",
        "feature_task",
    ]
    assert result["count"] == 3


def test_build_prism_review_activity_item_uses_canonical_shape() -> None:
    item = build_prism_review_activity_item(
        review_item_id="review-1",
        workspace_id="ws-1",
        latex_project_id="latex-1",
        logical_key="section:intro",
        title="sections/intro.tex",
        summary="Tighten introduction",
        status="applied",
        source_execution_id="exec-1",
        source_task_id="task-1",
        target_kind="prism_file_change",
        target_file_path="sections/intro.tex",
        target_room=None,
        target_item_id=None,
        occurred_at="2026-03-25T00:00:00Z",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-25T00:00:00Z",
        applied_at="2026-03-25T00:00:00Z",
    )

    assert item["id"] == "prism_review:review-1"
    assert item["kind"] == "prism_review"
    assert item["title"] == "已写入稿件修改: sections/intro.tex"
    assert item["summary"] == "Tighten introduction"
    assert item["status"] == "applied"
    assert item["task_id"] == "task-1"
    assert item["metadata"]["latex_project_id"] == "latex-1"
    assert item["metadata"]["source_execution_id"] == "exec-1"
    assert item["metadata"]["target_file_path"] == "sections/intro.tex"


@pytest.mark.asyncio
async def test_get_prism_review_activity_reads_persisted_items() -> None:
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    now = datetime.now(UTC)
    record = ReviewItemProjection(
        id="review-1",
        batch_id="batch-1",
        workspace_id="ws-1",
        source_item_id="section:intro",
        item_kind="file_change",
        target_domain="prism",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": "latex-1",
            "logical_key": "section:intro",
            "file_path": "sections/intro.tex",
        },
        title="sections/intro.tex",
        summary="Tighten introduction",
        status="rejected",
        payload_json={"source_execution_id": "exec-1", "source_task_id": "task-1"},
        preview_json={},
        provenance_json={},
        sort_order=0,
        created_at=now - timedelta(minutes=5),
        updated_at=now,
        applied_at=None,
    )
    fake_client.list_review_items = AsyncMock(return_value=[record])

    items = await service._get_prism_review_activity("ws-1", limit=10)

    fake_client.list_review_items.assert_awaited_once_with(
        workspace_id="ws-1",
        target_domain="prism",
        limit=10,
    )
    assert len(items) == 1
    assert items[0]["id"] == "prism_review:review-1"
    assert items[0]["kind"] == "prism_review"
    assert items[0]["status"] == "rejected"
    assert items[0]["occurred_at"] == now
    assert items[0]["metadata"]["source_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_get_recent_threads_uses_conversation_dataservice() -> None:
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        title="Research thread",
        skill="deep-research",
        updated_at=datetime.now(UTC),
    )
    fake_client.list_workspace_conversation_thread_summaries = AsyncMock(return_value=[thread])

    threads = await service._get_recent_threads("ws-1", limit=5)

    assert threads == [thread]
    fake_client.list_workspace_conversation_thread_summaries.assert_awaited_once_with(
        workspace_id="ws-1",
        limit=5,
    )


@pytest.mark.asyncio
async def test_build_thread_activity_uses_latest_message_preview_and_skill():
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        title="Literature review thread",
        skill="deep-research",
        updated_at=datetime.now(UTC),
        messages=[{"role": "user", "content": "raw bridge"}],
    )
    fake_client.list_conversation_messages = AsyncMock(
        return_value=[
            {"role": "user", "content": "Please review these papers."},
            {"role": "assistant", "content": "I found three themes across the literature."},
        ]
    )

    items = await service._build_thread_activity([thread], workspace_type="thesis")

    assert len(items) == 1
    assert items[0]["title"] == "Literature review thread"
    assert items[0]["summary"] == "I found three themes across the literature."
    assert items[0]["skill"] == "deep-research"
    assert items[0]["skill_name"] is None
    assert items[0]["metadata"]["skill"] == "deep-research"
    assert items[0]["metadata"]["skill_name"] is None
    fake_client.list_conversation_messages.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_build_thread_activity_includes_token_usage_metadata():
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    thread = SimpleNamespace(
        id="thread-usage",
        workspace_id="ws-1",
        title="Usage thread",
        skill="deep-research",
        updated_at=datetime.now(UTC),
        messages=[],
    )
    fake_client.list_conversation_messages = AsyncMock(
        return_value=[
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
        ]
    )

    items = await service._build_thread_activity([thread], workspace_type="thesis")

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
            "review_items": [
                {
                    "id": "review-1",
                    "kind": "prism_file_change",
                    "logical_key": "section:introduction",
                    "status": "pending",
                    "title": "Intro rewrite",
                    "target": {"file_path": "sections/introduction.tex"},
                }
            ],
        },
        occurred_at="2026-03-25T00:00:00Z",
        completed_at="2026-03-25T00:00:00Z",
    )

    assert {
        (action.get("action"), action.get("label"))
        for action in item["metadata"]["next_actions"]
    } >= {
        ("preview_prism_changes", "预览待确认修改"),
    }
    prism_action = next(
        action
        for action in item["metadata"]["next_actions"]
        if action.get("action") == "preview_prism_changes"
    )
    assert prism_action["review_item_id"] == "review-1"
    assert prism_action["logical_key"] == "section:introduction"


def test_task_record_to_activity_includes_token_usage_metadata() -> None:
    service = WorkspaceActivityService()
    record = _execution_projection(
        id="task-usage",
        execution_type="workspace_feature",
        capability_id="deep_research",
        task_brief_json={"topic": "LLM"},
        status="completed",
        progress=100,
        message="done",
        error_text=None,
        result_json={"summary": "ok"},
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
    service = WorkspaceActivityService()
    now = datetime.now(UTC)
    execution = _execution_projection(thread_id="thread-1")
    record = _node_projection(
        id="sub-usage",
        status="completed",
        node_type="scout",
        input_data={"prompt": "Find papers"},
        output_data={"output_preview": "Found 5 papers"},
        node_metadata={
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

    item = service._subagent_record_to_activity(record, execution)

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
    service = WorkspaceActivityService()
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
async def test_get_artifact_activity_reads_workspace_assets() -> None:
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    asset = _asset_projection(id="asset-1")
    fake_client.list_assets = AsyncMock(return_value=[asset])

    items = await service._get_artifact_activity("ws-1", workspace_type="thesis", limit=10)

    fake_client.list_assets.assert_awaited_once_with(
        workspace_id="ws-1",
        include_deleted=False,
        limit=10,
    )
    assert items[0]["id"] == "artifact:asset-1"
    assert items[0]["artifact_id"] == "asset-1"
    assert items[0]["status"] == "draft"
    assert items[0]["metadata"]["asset_kind"] == "figure"
    assert items[0]["metadata"]["version"] == 2


@pytest.mark.asyncio
async def test_get_subagent_activity_reads_persisted_records() -> None:
    fake_client = FakeActivityDataServiceClient()
    service = WorkspaceActivityService(dataservice=fake_client)
    now = datetime.now(UTC)
    created_at = now - timedelta(minutes=5)
    execution = _execution_projection(id="exec-1", thread_id="thread-1")
    record = _node_projection(
        id="sub-1",
        execution_id="exec-1",
        status="completed",
        node_type="paper_critic",
        input_data={"prompt": "Review this paper"},
        output_data={"output_preview": "Found three issues"},
        created_at=created_at,
        updated_at=now - timedelta(minutes=1),
        completed_at=now,
    )
    fake_client.list_executions = AsyncMock(return_value=[execution])
    fake_client.list_execution_nodes_by_execution_ids = AsyncMock(return_value=[record])

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
