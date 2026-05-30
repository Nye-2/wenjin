"""Tests for task-to-thread result write-back."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.tasks.base import (
    _append_task_thread_message,
    _resolve_thread_skill,
    _sync_document_preprocess_attachment_state,
    _sync_reference_preprocess_attachment_state,
)


def _thread(thread_id: str, *, workspace_id: str = "ws-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=thread_id,
        user_id="user-1",
        workspace_id=workspace_id,
        title=None,
        model="gpt-test",
        skill=None,
        message_count=0,
        last_message_role=None,
        last_message_preview=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _message_with_attachment(task_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        role="user",
        content="uploaded file",
        timestamp=datetime.now(UTC),
        metadata_json={
            "attachments": [
                {
                    "name": "paper.pdf",
                    "metadata": {
                        "preprocess": {
                            "task_id": task_id,
                            "status": "running",
                        }
                    },
                }
            ]
        },
        blocks=[],
    )


def _dataservice(thread: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        get_conversation_thread=AsyncMock(return_value=thread),
        append_conversation_message=AsyncMock(
            return_value=SimpleNamespace(sequence_index=0, timestamp=datetime.now(UTC))
        ),
        lock_conversation_thread=AsyncMock(return_value=True),
        list_conversation_messages=AsyncMock(return_value=[]),
        update_conversation_thread=AsyncMock(return_value=thread),
        rebuild_conversation_messages=AsyncMock(),
    )


def test_resolve_thread_skill_prefers_canonical_skill_payload() -> None:
    assert _resolve_thread_skill(
        {
            "skill_id": "figure-designer",
            "skill_name": "图表设计",
            "feature_id": "figure_generation",
        },
        "workspace_feature",
    ) == ("figure-designer", "图表设计")


def test_resolve_thread_skill_falls_back_when_payload_lacks_skill() -> None:
    assert _resolve_thread_skill(
        {"feature_id": "figure_generation"},
        "workspace_feature",
    ) == ("figure_generation", None)


@pytest.mark.asyncio
async def test_append_task_thread_message_writes_completion_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread("thread-1")
    dataservice = _dataservice(thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_thread_message(
        dataservice=dataservice,
        task_id="task-1",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-1",
            "feature_id": "thesis_research_pack",
            "params": {"topic": "LLM planning"},
        },
        result={
            "data": {"sections": [{"title": "Intro"}, {"title": "Method"}]},
            "artifacts": [{"id": "artifact-1", "title": "LLM Framework"}],
        },
    )

    dataservice.append_conversation_message.assert_awaited_once()
    _, command = dataservice.append_conversation_message.await_args.args
    assert command.role == "assistant"
    assert len(command.blocks) == 1
    block = command.blocks[0]
    assert block["kind"] == "result_card"
    assert block["title"].startswith("论文研究包")
    assert "已完成" in block["title"]
    assert {
        (link.get("label"), link.get("href"))
        for link in block["links"]
    } >= {
        (
            "基于当前产物继续",
            "/workspaces/ws-1?feature=thesis_research_pack&topic=LLM+planning&source_artifact_id=artifact-1&context_artifact_ids=artifact-1",
        ),
    }
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_append_task_thread_message_writes_failure_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread("thread-2")
    dataservice = _dataservice(thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_thread_message(
        dataservice=dataservice,
        task_id="task-2",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-2",
            "feature_id": "peer_review",
            "params": {"paper_title": "Agent Paper"},
        },
        error="tool timeout",
    )

    dataservice.append_conversation_message.assert_awaited_once()
    _, command = dataservice.append_conversation_message.await_args.args
    assert command.role == "assistant"
    assert len(command.blocks) == 1
    block = command.blocks[0]
    assert block["kind"] == "result_card"
    assert "失败" in block["title"]
    assert "tool timeout" in block["tldr"]
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_append_task_thread_message_skips_reference_preprocess(
) -> None:
    dataservice = _dataservice(_thread("thread-3"))

    await _append_task_thread_message(
        dataservice=dataservice,
        task_id="task-3",
        task_type="reference_preprocess",
        payload={
            "thread_id": "thread-3",
            "reference_id": "reference-1",
        },
        result={"message": "Reference preprocessing completed"},
    )

    dataservice.append_conversation_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_append_task_thread_message_skips_document_preprocess(
) -> None:
    dataservice = _dataservice(_thread("thread-3b"))

    await _append_task_thread_message(
        dataservice=dataservice,
        task_id="task-3b",
        task_type="document_preprocess",
        payload={
            "thread_id": "thread-3b",
            "filename": "paper.pdf",
        },
        result={"message": "Document preprocessing completed"},
    )

    dataservice.append_conversation_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_reference_preprocess_attachment_state_updates_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread("thread-4")
    dataservice = _dataservice(thread)
    dataservice.list_conversation_messages.return_value = [_message_with_attachment("task-4")]
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _sync_reference_preprocess_attachment_state(
        dataservice=dataservice,
        task_id="task-4",
        task_type="reference_preprocess",
        payload={
            "thread_id": "thread-4",
            "reference_id": "reference-1",
        },
        status="success",
        result={"preprocess": {"status": "succeeded"}},
        message="Reference preprocessing completed",
        progress=100,
        current_step="complete",
    )

    dataservice.lock_conversation_thread.assert_awaited_once_with("thread-4")
    dataservice.update_conversation_thread.assert_awaited_once()
    dataservice.rebuild_conversation_messages.assert_awaited_once()
    _, command = dataservice.rebuild_conversation_messages.await_args.args
    attachment = command.messages[0]["metadata"]["attachments"][0]
    preprocess = attachment["metadata"]["preprocess"]
    assert preprocess["task_id"] == "task-4"
    assert preprocess["status"] == "succeeded"
    assert preprocess["message"] == "Reference preprocessing completed"
    assert preprocess["progress"] == 100
    assert preprocess["current_step"] == "complete"
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_sync_document_preprocess_attachment_state_updates_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread("thread-5")
    dataservice = _dataservice(thread)
    dataservice.list_conversation_messages.return_value = [_message_with_attachment("task-5")]
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _sync_document_preprocess_attachment_state(
        dataservice=dataservice,
        task_id="task-5",
        task_type="document_preprocess",
        payload={
            "thread_id": "thread-5",
            "filename": "paper.pdf",
        },
        status="success",
        result={
            "preprocess": {
                "status": "succeeded",
                "markdown_paths": ["/context/_preprocessed/background/doc_0.md"],
            }
        },
        message="Document preprocessing completed",
        progress=100,
        current_step="complete",
    )

    dataservice.lock_conversation_thread.assert_awaited_once_with("thread-5")
    dataservice.update_conversation_thread.assert_awaited_once()
    dataservice.rebuild_conversation_messages.assert_awaited_once()
    _, command = dataservice.rebuild_conversation_messages.await_args.args
    attachment = command.messages[0]["metadata"]["attachments"][0]
    preprocess = attachment["metadata"]["preprocess"]
    assert preprocess["task_id"] == "task-5"
    assert preprocess["status"] == "succeeded"
    assert preprocess["markdown_paths"] == ["/context/_preprocessed/background/doc_0.md"]
    assert attachment["metadata"]["preprocessed_markdown_paths"] == [
        "/context/_preprocessed/background/doc_0.md"
    ]
    publish_thread_updated.assert_awaited_once_with(thread)
