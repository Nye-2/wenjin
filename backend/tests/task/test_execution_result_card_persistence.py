"""Tests for execution completion result_card persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.tasks.execution import (
    _persist_result_card_for_execution,
    _result_card_data_from_task_report,
)


def test_result_card_data_from_task_report_preserves_outputs_and_reviews() -> None:
    task_report = {
        "execution_id": "exec-1",
        "capability_id": "sci_literature_positioning",
        "status": "completed",
        "narrative": "完成文献定位。",
        "duration_seconds": 12,
        "outputs": [
            {
                "id": "out-1",
                "kind": "document",
                "preview": "定位报告",
                "default_checked": True,
                "data": {"name": "文献定位与创新点.md"},
            }
        ],
        "review_items": [
            {
                "id": "review-1",
                "kind": "prism_file_change",
                "status": "pending",
            }
        ],
    }

    data = _result_card_data_from_task_report("fallback-exec", task_report)

    assert data["execution_id"] == "exec-1"
    assert data["capability_name"] == "sci_literature_positioning"
    assert data["status"] == "completed"
    assert data["narrative"] == "完成文献定位。"
    assert data["duration_seconds"] == 12
    assert data["outputs"] == [
        {
            "id": "out-1",
            "kind": "document",
            "preview": "定位报告",
            "default_checked": True,
            "data": {"name": "文献定位与创新点.md"},
        }
    ]
    assert data["review_items"] == [
        {
            "id": "review-1",
            "kind": "prism_file_change",
            "status": "pending",
        }
    ]
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_persist_result_card_for_execution_appends_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-1", user_id="user-1", workspace_id="ws-1", message_count=0)
    service = SimpleNamespace(
        get_by_id=AsyncMock(return_value=thread),
        list_thread_messages=AsyncMock(return_value=[]),
        add_message=AsyncMock(),
    )

    monkeypatch.setattr("src.services.ThreadService", lambda db: service)

    execution = SimpleNamespace(
        id="exec-1",
        thread_id="thread-1",
        result={
            "task_report": {
                "execution_id": "exec-1",
                "capability_id": "sci_literature_positioning",
                "status": "completed",
                "narrative": "完成 文献定位与创新点，共执行 3 个节点。",
                "outputs": [
                    {
                        "id": "out-1",
                        "kind": "document",
                        "preview": "定位报告",
                        "data": {"name": "文献定位与创新点.md"},
                    }
                ],
            }
        },
    )

    await _persist_result_card_for_execution(object(), execution)

    service.add_message.assert_awaited_once()
    kwargs = service.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert kwargs["content"] == "完成 文献定位与创新点，共执行 3 个节点。"
    assert kwargs["metadata"] == {
        "source": "execution_completion",
        "execution_id": "exec-1",
    }
    assert kwargs["blocks"] == [
        {
            "kind": "result_card",
            "data": {
                "execution_id": "exec-1",
                "capability_name": "sci_literature_positioning",
                "status": "completed",
                "outputs": [
                    {
                        "id": "out-1",
                        "kind": "document",
                        "preview": "定位报告",
                        "default_checked": True,
                        "data": {"name": "文献定位与创新点.md"},
                    }
                ],
                "review_items": None,
                "narrative": "完成 文献定位与创新点，共执行 3 个节点。",
                "duration_seconds": None,
                "errors": [],
            },
        }
    ]

    service.list_thread_messages.return_value = [
        {
            "role": "assistant",
            "blocks": [
                {
                    "kind": "result_card",
                    "data": {"execution_id": "exec-1"},
                }
            ],
        }
    ]

    await _persist_result_card_for_execution(object(), execution)

    service.add_message.assert_awaited_once()
