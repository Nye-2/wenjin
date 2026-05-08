"""Tests for task-to-thread result write-back."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.tasks.base import (
    _append_task_thread_message,
    _resolve_thread_skill,
    _sync_document_preprocess_attachment_state,
    _sync_reference_preprocess_attachment_state,
)


class _FakeThreadService:
    def __init__(self, db, thread):
        self._thread = thread
        self.add_message = AsyncMock()

    async def get_by_id(self, thread_id: str):
        if self._thread and self._thread.id == thread_id:
            return self._thread
        return None


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
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1")
    service = _FakeThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_thread_message(
        db=object(),
        task_id="task-1",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-1",
            "feature_id": "framework_outline",
            "params": {"topic": "LLM planning"},
        },
        result={
            "data": {"sections": [{"title": "Intro"}, {"title": "Method"}]},
            "artifacts": [{"id": "artifact-1", "title": "LLM Framework"}],
        },
    )

    service.add_message.assert_awaited_once()
    kwargs = service.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert len(kwargs["blocks"]) == 1
    block = kwargs["blocks"][0]
    assert block["kind"] == "result_card"
    assert block["title"].startswith("框架大纲")
    assert "已完成" in block["title"]
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_append_task_thread_message_writes_failure_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-2", workspace_id="ws-1")
    service = _FakeThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_thread_message(
        db=object(),
        task_id="task-2",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-2",
            "feature_id": "peer_review",
            "params": {"paper_title": "Agent Paper"},
        },
        error="tool timeout",
    )

    service.add_message.assert_awaited_once()
    kwargs = service.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert len(kwargs["blocks"]) == 1
    block = kwargs["blocks"][0]
    assert block["kind"] == "result_card"
    assert "失败" in block["title"]
    assert "tool timeout" in block["tldr"]
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_append_task_thread_message_skips_reference_preprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-3", workspace_id="ws-1")
    service = _FakeThreadService(object(), thread)

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )

    await _append_task_thread_message(
        db=object(),
        task_id="task-3",
        task_type="reference_preprocess",
        payload={
            "thread_id": "thread-3",
            "reference_id": "reference-1",
        },
        result={"message": "Reference preprocessing completed"},
    )

    service.add_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_append_task_thread_message_skips_document_preprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-3b", workspace_id="ws-1")
    service = _FakeThreadService(object(), thread)

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )

    await _append_task_thread_message(
        db=object(),
        task_id="task-3b",
        task_type="document_preprocess",
        payload={
            "thread_id": "thread-3b",
            "filename": "paper.pdf",
        },
        result={"message": "Document preprocessing completed"},
    )

    service.add_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_reference_preprocess_attachment_state_updates_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-4", workspace_id="ws-1")

    class _SyncingThreadService(_FakeThreadService):
        def __init__(self, db, thread):
            super().__init__(db, thread)
            self.update_attachment_preprocess_state = AsyncMock(return_value=True)

    service = _SyncingThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _sync_reference_preprocess_attachment_state(
        db=object(),
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

    service.update_attachment_preprocess_state.assert_awaited_once_with(
        thread,
        task_id="task-4",
        status="success",
        preprocess={"status": "succeeded"},
        message="Reference preprocessing completed",
        progress=100,
        current_step="complete",
        error=None,
    )
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_sync_document_preprocess_attachment_state_updates_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-5", workspace_id="ws-1")

    class _SyncingThreadService(_FakeThreadService):
        def __init__(self, db, thread):
            super().__init__(db, thread)
            self.update_attachment_preprocess_state = AsyncMock(return_value=True)

    service = _SyncingThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.thread_service.ThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _sync_document_preprocess_attachment_state(
        db=object(),
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

    service.update_attachment_preprocess_state.assert_awaited_once_with(
        thread,
        task_id="task-5",
        status="success",
        preprocess={
            "status": "succeeded",
            "markdown_paths": ["/context/_preprocessed/background/doc_0.md"],
        },
        message="Document preprocessing completed",
        progress=100,
        current_step="complete",
        error=None,
    )
    publish_thread_updated.assert_awaited_once_with(thread)
